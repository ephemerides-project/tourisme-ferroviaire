"""Stockage et enrichissement : écrit les tables propres dans PostgreSQL/PostGIS,
puis calcule les rapprochements entre sources (gare <-> POI, accessibilité entre gares).
"""

from __future__ import annotations

import math

import pandas as pd
import psycopg
from psycopg.types.json import Jsonb

from app import config

TABLES = ["import_journal", "accessibilite", "liaison", "gare_poi", "poi", "gare_uic", "gare"]


def _valeur(v):
    """Convertit les valeurs « vides » de pandas (NaN, NaT, NA, chaîne vide) en NULL."""
    if v is None or isinstance(v, (list, tuple, Jsonb)):
        return v
    if isinstance(v, float) and math.isnan(v):
        return None
    if v is pd.NA or v is pd.NaT or v == "":
        return None
    return v


def _copier(cur: psycopg.Cursor, table: str, colonnes: list[str], lignes) -> int:
    """Insertion en masse avec COPY, bien plus rapide que des INSERT ligne à ligne."""
    n = 0
    with cur.copy(f"COPY {table} ({', '.join(colonnes)}) FROM STDIN") as copie:
        for ligne in lignes:
            copie.write_row([_valeur(v) for v in ligne])
            n += 1
    return n


def appliquer_schema(conn: psycopg.Connection) -> None:
    conn.execute(config.SCHEMA_SQL.read_text(encoding="utf-8"))


def charger(conn: psycopg.Connection, gares: pd.DataFrame, liaisons: pd.DataFrame, poi: pd.DataFrame) -> dict:
    """Remplace tout le contenu de la base par les tables fournies (dans une seule transaction)."""
    bilan: dict = {}
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")

        col_gare = ["id", "nom", "trigramme", "code_insee", "departement", "segment_drg", "lat", "lon"]
        bilan["gare"] = _copier(cur, "gare", col_gare, gares[col_gare].itertuples(index=False))
        bilan["gare_uic"] = _copier(
            cur, "gare_uic", ["uic", "gare_id"], ((uic, g.id) for g in gares.itertuples() for uic in g.codes_uic)
        )

        col_poi = ["id", "nom", "themes", "types_source", "lat", "lon", "commune", "code_postal", "description", "source", "maj"]
        bilan["poi"] = _copier(cur, "poi", col_poi, poi[col_poi].itertuples(index=False))

        col_liaison = ["origine_id", "destination_id", "duree_min", "trajets_jour", "trace"]
        bilan["liaison"] = _copier(
            cur,
            "liaison",
            col_liaison,
            (
                (l.origine_id, l.destination_id, l.duree_min, l.trajets_jour, Jsonb(l.trace) if l.trace else None)
                for l in liaisons[col_liaison].itertuples(index=False)
            ),
        )

        bilan.update(enrichir(cur))
    return bilan


def enrichir(cur: psycopg.Cursor) -> dict:
    """Rapprochements entre sources, entièrement en SQL."""
    bilan: dict = {}

    # 1. Chaque POI est rattaché aux gares situées dans le rayon de marche.
    cur.execute(
        """
        INSERT INTO gare_poi (gare_id, poi_id, distance_m, marche_min)
        SELECT g.id, p.id, d.distance_m,
               GREATEST(1, CEIL(d.distance_m * %(detour)s / %(vitesse)s))::int
        FROM gare g
        JOIN poi p ON ST_DWithin(g.geog, p.geog, %(rayon)s)
        CROSS JOIN LATERAL (SELECT ROUND(ST_Distance(g.geog, p.geog))::int AS distance_m) d
        """,
        {"rayon": float(config.RAYON_POI_M), "detour": config.FACTEUR_DETOUR, "vitesse": config.VITESSE_MARCHE_M_MIN},
    )
    bilan["gare_poi"] = cur.rowcount

    # 2. Une gare est « desservie » si elle apparaît dans au moins une liaison.
    cur.execute(
        """
        UPDATE gare SET desservie = EXISTS (
            SELECT 1 FROM liaison l WHERE l.origine_id = gare.id OR l.destination_id = gare.id
        )
        """
    )

    # 3. Accessibilité : d'abord les liaisons directes...
    cur.execute(
        """
        INSERT INTO accessibilite (origine_id, destination_id, duree_min, correspondances, via_id, trajets_jour)
        SELECT origine_id, destination_id, duree_min, 0, NULL, trajets_jour FROM liaison
        """
    )
    bilan["accessibilite_directe"] = cur.rowcount

    # ... puis, pour les couples sans liaison directe, le meilleur trajet à une correspondance.
    cur.execute(
        """
        INSERT INTO accessibilite (origine_id, destination_id, duree_min, correspondances, via_id, trajets_jour)
        SELECT DISTINCT ON (a.origine_id, b.destination_id)
               a.origine_id, b.destination_id,
               a.duree_min + b.duree_min + %(marge)s, 1, a.destination_id,
               LEAST(a.trajets_jour, b.trajets_jour)
        FROM liaison a
        JOIN liaison b ON b.origine_id = a.destination_id
        WHERE b.destination_id <> a.origine_id
          AND a.duree_min + b.duree_min + %(marge)s <= %(duree_max)s
          AND NOT EXISTS (
              SELECT 1 FROM liaison d
              WHERE d.origine_id = a.origine_id AND d.destination_id = b.destination_id
          )
        ORDER BY a.origine_id, b.destination_id, a.duree_min + b.duree_min
        """,
        {"marge": config.MARGE_CORRESPONDANCE_MIN, "duree_max": config.DUREE_MAX_CORRESPONDANCE_MIN},
    )
    bilan["accessibilite_correspondance"] = cur.rowcount
    return bilan


def journaliser(conn: psycopg.Connection, entrees: list[tuple[str, str, int]]) -> None:
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany("INSERT INTO import_journal (source, detail, lignes) VALUES (%s, %s, %s)", entrees)
