"""Gares de voyageurs — source : SNCF Open Data (jeu « gares-de-voyageurs »).

Étapes couvertes : lecture, nettoyage, normalisation, filtrage sur la région.

Les exports SNCF existent en JSON (noms techniques) et en CSV (libellés). Les noms
de champs ont déjà changé d'une version à l'autre du jeu de données : on retrouve
donc chaque champ par mots-clés plutôt que par nom exact.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pandas as pd

from app import config
from app.texte import cle

COLONNES = ["id", "nom", "trigramme", "code_insee", "departement", "segment_drg", "lat", "lon", "codes_uic"]


def lire_gares(chemin: Path) -> list[dict]:
    """Lit l'export SNCF, en JSON (liste d'objets) ou en CSV (séparateur `;`)."""
    if chemin.suffix.lower() == ".json":
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        # L'API « records » enveloppe la liste dans {"results": [...]}.
        return donnees.get("results", []) if isinstance(donnees, dict) else donnees
    with chemin.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def _champ(enregistrement: dict, *mots_cles: str):
    """Première valeur dont le nom de champ contient l'un des mots-clés."""
    for mot in mots_cles:
        for nom, valeur in enregistrement.items():
            if mot in cle(nom) and valeur not in (None, ""):
                return valeur
    return None


def _position(valeur) -> tuple[float, float] | None:
    """Renvoie (lat, lon) quel que soit le format rencontré."""
    try:
        if isinstance(valeur, dict):
            if "lat" in valeur and "lon" in valeur:
                return float(valeur["lat"]), float(valeur["lon"])
            if "coordinates" in valeur:  # GeoJSON : [lon, lat]
                lon, lat = valeur["coordinates"][:2]
                return float(lat), float(lon)
        if isinstance(valeur, (list, tuple)) and len(valeur) >= 2:
            return float(valeur[0]), float(valeur[1])
        if isinstance(valeur, str):  # CSV : « 45.1915, 5.7145 »
            lat, lon = (float(x) for x in valeur.split(",")[:2])
            return lat, lon
    except (TypeError, ValueError):
        pass
    return None


def codes_uic(valeur) -> list[str]:
    """« 87747006;87747337 » -> ['87747006', '87747337'] (8 derniers chiffres de chaque code)."""
    if valeur is None:
        return []
    if isinstance(valeur, (list, tuple)):
        valeur = ";".join(str(v) for v in valeur)
    codes = []
    for groupe in re.findall(r"\d{7,}", str(valeur)):
        code = groupe[-8:]
        if code not in codes:
            codes.append(code)
    return codes


def dans_la_region(code_insee: str | None, lat: float, lon: float) -> bool:
    """Filtre régional : par département si le code INSEE est connu, sinon par boîte englobante."""
    if code_insee:
        return code_insee[:2] in config.DEPARTEMENTS
    lat_min, lat_max, lon_min, lon_max = config.BOITE_REGION
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def normaliser_gares(enregistrements: list[dict]) -> tuple[pd.DataFrame, dict]:
    """Transforme les enregistrements bruts en table propre + un petit bilan de nettoyage."""
    lignes, bilan = [], {"lues": len(enregistrements), "sans_position": 0, "sans_uic": 0, "hors_region": 0, "doublons": 0}
    vus: set[str] = set()
    for e in enregistrements:
        position = _position(_champ(e, "positiongeo", "geopoint", "coordonnees", "position"))
        if position is None:
            bilan["sans_position"] += 1
            continue
        uics = codes_uic(_champ(e, "uic"))
        if not uics:
            bilan["sans_uic"] += 1
            continue
        lat, lon = position
        insee = _champ(e, "insee", "codecommune")
        insee = str(insee).strip().zfill(5) if insee else None
        if not dans_la_region(insee, lat, lon):
            bilan["hors_region"] += 1
            continue
        if uics[0] in vus:
            bilan["doublons"] += 1
            continue
        vus.add(uics[0])
        segment = _champ(e, "segment")
        lignes.append(
            {
                "id": uics[0],
                "nom": str(_champ(e, "nomgare", "nom", "libelle") or "").strip(),
                "trigramme": _champ(e, "trigramme", "libellecourt"),
                "code_insee": insee,
                "departement": insee[:2] if insee else None,
                "segment_drg": ";".join(segment) if isinstance(segment, list) else segment,
                "lat": lat,
                "lon": lon,
                "codes_uic": uics,
            }
        )
    gares = pd.DataFrame(lignes, columns=COLONNES)
    gares = gares[gares["nom"] != ""].reset_index(drop=True)
    bilan["retenues"] = len(gares)
    return gares, bilan
