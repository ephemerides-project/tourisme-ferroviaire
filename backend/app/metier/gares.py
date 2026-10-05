"""Logique métier « Explorer » : gares et points d'intérêt. Aucun LLM ici."""

from __future__ import annotations

import psycopg

from app.texte import normaliser


def lister_gares(conn: psycopg.Connection, q: str | None = None, desservies_seulement: bool = True) -> list[dict]:
    """Gares de la région, avec le nombre de points d'intérêt rattachés à chacune."""
    return conn.execute(
        """
        SELECT g.id, g.nom, g.lat, g.lon, g.departement, g.desservie,
               (SELECT count(*) FROM gare_poi gp WHERE gp.gare_id = g.id) AS nb_poi
        FROM gare g
        WHERE (NOT %(desservies)s OR g.desservie)
          AND (%(q)s::text IS NULL OR unaccent(lower(g.nom)) LIKE '%%' || unaccent(lower(%(q)s::text)) || '%%')
        ORDER BY g.nom
        """,
        {"q": q or None, "desservies": desservies_seulement},
    ).fetchall()


def trouver_gare(conn: psycopg.Connection, gare_id: str) -> dict | None:
    return conn.execute(
        "SELECT id, nom, trigramme, code_insee, departement, segment_drg, lat, lon, desservie FROM gare WHERE id = %s",
        (gare_id,),
    ).fetchone()


def resoudre_gare(conn: psycopg.Connection, texte: str) -> dict | None:
    """Retrouve la gare désignée par un nom libre (« Grenoble », « lyon », « Chambéry »).

    Ordre de préférence : nom identique, nom commençant par le texte, nom contenant le texte.
    À égalité, on prend la gare la mieux desservie (« Lyon » -> la gare lyonnaise qui a le plus de liaisons).
    """
    cherche = normaliser(texte)
    if not cherche:
        return None
    gares = conn.execute(
        """
        SELECT g.id, g.nom, g.lat, g.lon,
               (SELECT count(*) FROM liaison l WHERE l.origine_id = g.id) AS nb_liaisons
        FROM gare g
        """
    ).fetchall()
    candidates = []
    for gare in gares:
        nom = normaliser(gare["nom"])
        if nom == cherche:
            rang = 0
        elif nom.startswith(cherche + " "):
            rang = 1
        elif f" {cherche} " in f" {nom} ":
            rang = 2
        else:
            continue
        candidates.append((rang, -gare["nb_liaisons"], gare["nom"], gare))
    if not candidates:
        return None
    meilleure = min(candidates, key=lambda c: c[:3])[3]
    return {k: meilleure[k] for k in ("id", "nom", "lat", "lon")}


def poi_proches(
    conn: psycopg.Connection,
    gare_id: str,
    themes: list[str] | None = None,
    marche_max: int | None = None,
    limite: int = 100,
) -> list[dict]:
    """Points d'intérêt rattachés à une gare, du plus proche au plus lointain."""
    return conn.execute(
        """
        SELECT p.id, p.nom, p.themes, p.lat, p.lon, p.commune, p.description, p.source,
               gp.distance_m, gp.marche_min
        FROM gare_poi gp
        JOIN poi p ON p.id = gp.poi_id
        WHERE gp.gare_id = %(gare)s
          AND (%(marche)s::int IS NULL OR gp.marche_min <= %(marche)s::int)
          AND (cardinality(%(themes)s::text[]) = 0 OR p.themes && %(themes)s::text[])
        ORDER BY gp.distance_m
        LIMIT %(limite)s
        """,
        {"gare": gare_id, "marche": marche_max, "themes": themes or [], "limite": limite},
    ).fetchall()


def statistiques(conn: psycopg.Connection) -> dict:
    """Volumes réellement chargés et journal des imports : utile pour la démonstration."""
    volumes = conn.execute(
        """
        SELECT (SELECT count(*) FROM gare) AS gares,
               (SELECT count(*) FROM gare WHERE desservie) AS gares_desservies,
               (SELECT count(*) FROM liaison) AS liaisons_directes,
               (SELECT count(*) FROM accessibilite WHERE correspondances = 1) AS trajets_avec_correspondance,
               (SELECT count(*) FROM poi) AS points_interet,
               (SELECT count(*) FROM gare_poi) AS rattachements_gare_poi
        """
    ).fetchone()
    par_theme = conn.execute(
        "SELECT theme, count(*) AS nb FROM poi, unnest(themes) AS theme GROUP BY theme ORDER BY nb DESC"
    ).fetchall()
    imports = conn.execute("SELECT source, detail, lignes, termine_le FROM import_journal ORDER BY id").fetchall()
    return {"volumes": volumes, "poi_par_theme": par_theme, "imports": imports}
