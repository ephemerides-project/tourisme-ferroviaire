"""Logique métier « destinations accessibles » : recherche en base puis classement.

C'est cette fonction qui choisit les destinations. Le LLM n'intervient ni avant
(il ne fournit que des critères) ni après (il ne fait que rédiger).
"""

from __future__ import annotations

import psycopg

from app.metier import scoring
from app.themes import THEMES_ACTIVITE

NB_POI_PAR_DESTINATION = 5


def rechercher(
    conn: psycopg.Connection,
    origine_id: str,
    duree_max: int,
    themes: list[str],
    marche_max: int,
    limite: int = 5,
) -> tuple[list[dict], dict]:
    """Destinations accessibles depuis `origine_id`, classées. Renvoie (destinations, diagnostic)."""
    # Sans thème demandé, on cherche des activités : ni hébergements, ni événements non datés.
    themes_cherches = themes or list(THEMES_ACTIVITE)
    # 1. Gares accessibles dans le temps imparti.
    accessibles = conn.execute(
        """
        SELECT a.destination_id AS id, g.nom, g.lat, g.lon,
               a.duree_min, a.correspondances, a.trajets_jour, v.nom AS via
        FROM accessibilite a
        JOIN gare g ON g.id = a.destination_id
        LEFT JOIN gare v ON v.id = a.via_id
        WHERE a.origine_id = %s AND a.duree_min <= %s
        """,
        (origine_id, duree_max),
    ).fetchall()
    diagnostic = {"gares_accessibles": len(accessibles), "gares_avec_offre": 0}
    if not accessibles:
        return [], diagnostic

    # 2. Points d'intérêt correspondant aux thèmes, à distance de marche de ces gares.
    pois = conn.execute(
        """
        SELECT gp.gare_id, p.id, p.nom, p.themes, p.lat, p.lon, p.commune, gp.distance_m, gp.marche_min
        FROM gare_poi gp
        JOIN poi p ON p.id = gp.poi_id
        WHERE gp.gare_id = ANY(%(gares)s)
          AND gp.marche_min <= %(marche)s
          AND cardinality(p.themes) > 0
          AND (cardinality(%(themes)s::text[]) = 0 OR p.themes && %(themes)s::text[])
        """,
        {"gares": [g["id"] for g in accessibles], "marche": marche_max, "themes": themes_cherches},
    ).fetchall()
    pois_par_gare: dict[str, list[dict]] = {}
    for poi in pois:
        pois_par_gare.setdefault(poi.pop("gare_id"), []).append(poi)
    diagnostic["gares_avec_offre"] = len(pois_par_gare)

    # 3. Si rien ne correspond, on cherche quelle contrainte bloque (pour le dire à l'utilisateur).
    if not pois_par_gare:
        diagnostic.update(_contrainte_bloquante(conn, origine_id, [g["id"] for g in accessibles], themes_cherches))
        return [], diagnostic

    # 4. Classement.
    destinations = []
    for gare in accessibles:
        pois_gare = pois_par_gare.get(gare["id"])
        if not pois_gare:
            continue
        score = scoring.calculer(
            gare["duree_min"], duree_max, gare["correspondances"], gare["trajets_jour"], pois_gare, themes, marche_max
        )
        # Les POI couvrant le plus de thèmes demandés d'abord, puis les plus proches.
        pois_gare.sort(key=lambda p: (-len(set(p["themes"]) & set(themes)), p["marche_min"]))
        destinations.append(
            {
                "gare": {"id": gare["id"], "nom": gare["nom"], "lat": gare["lat"], "lon": gare["lon"]},
                "trajet": {
                    "duree_min": gare["duree_min"],
                    "correspondances": gare["correspondances"],
                    "via": gare["via"],
                    "trajets_jour": gare["trajets_jour"],
                    "duree_estimee": gare["correspondances"] > 0,
                },
                "score": score["total"],
                "detail_score": score,
                "nb_pois": len(pois_gare),
                "pois": pois_gare[:NB_POI_PAR_DESTINATION],
            }
        )
    destinations.sort(key=lambda d: (-d["score"], d["trajet"]["duree_min"]))
    return destinations[:limite], diagnostic


def _contrainte_bloquante(conn: psycopg.Connection, origine_id: str, gares: list[str], themes: list[str]) -> dict:
    """Quand la recherche est vide : jusqu'où faudrait-il assouplir la marche ou le temps de trajet ?"""
    sans_limite_marche = conn.execute(
        """
        SELECT min(gp.marche_min) AS marche_min
        FROM gare_poi gp JOIN poi p ON p.id = gp.poi_id
        WHERE gp.gare_id = ANY(%(gares)s) AND cardinality(p.themes) > 0
          AND (cardinality(%(themes)s::text[]) = 0 OR p.themes && %(themes)s::text[])
        """,
        {"gares": gares, "themes": themes},
    ).fetchone()
    sans_limite_trajet = conn.execute(
        """
        SELECT min(a.duree_min) AS duree_min
        FROM accessibilite a
        WHERE a.origine_id = %(origine)s AND EXISTS (
            SELECT 1 FROM gare_poi gp JOIN poi p ON p.id = gp.poi_id
            WHERE gp.gare_id = a.destination_id AND cardinality(p.themes) > 0
              AND (cardinality(%(themes)s::text[]) = 0 OR p.themes && %(themes)s::text[])
        )
        """,
        {"origine": origine_id, "themes": themes},
    ).fetchone()
    return {
        "marche_min_necessaire": sans_limite_marche["marche_min"],
        "duree_min_necessaire": sans_limite_trajet["duree_min"],
    }
