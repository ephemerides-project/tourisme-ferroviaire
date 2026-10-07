"""Points d'intérêt — source : DATAtourisme (export CSV régional sur data.gouv.fr).

Étapes couvertes : lecture, nettoyage (coordonnées invalides, doublons, hors région),
normalisation (colonnes, thèmes internes).
"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from pathlib import Path

import pandas as pd

from app import config
from app.texte import cle
from app.services import TYPES_DATATOURISME
from app.themes import classer, enrichir_par_texte, est_classe, nom_local

COLONNES = ["id", "nom", "themes", "types_source", "lat", "lon", "commune", "code_postal", "description", "source", "maj"]
SOURCE = "DATAtourisme"

# colonne interne -> mots-clés cherchés dans les en-têtes du CSV (par ordre de préférence)
EN_TETES = {
    "nom": ("nomdupoi", "nom", "label", "titre"),
    "types": ("categoriesdepoi", "categorie", "type"),
    "lat": ("latitude",),
    "lon": ("longitude",),
    "commune": ("codepostaletcommune", "commune"),
    "description": ("description",),
    "id": ("uriiddupoi", "uri", "identifiant"),
    "maj": ("datedemiseajour", "miseajour"),
}


def lire_csv(chemin: Path) -> pd.DataFrame:
    """Lit le CSV en texte, en détectant le séparateur sur la première ligne."""
    with chemin.open(encoding="utf-8-sig", newline="") as f:
        premiere_ligne = f.readline()
    try:
        separateur = csv.Sniffer().sniff(premiere_ligne, delimiters=",;\t").delimiter
    except csv.Error:
        separateur = ","
    return pd.read_csv(chemin, dtype=str, sep=separateur, encoding="utf-8-sig", keep_default_na=False)


def reperer_colonnes(colonnes: list[str]) -> dict[str, str]:
    """Associe nos noms internes aux en-têtes réels du fichier."""
    par_cle = {cle(c): c for c in colonnes}
    trouvees: dict[str, str] = {}
    for interne, mots in EN_TETES.items():
        for mot in mots:
            candidates = [c for k, c in par_cle.items() if mot in k]
            if candidates:
                trouvees[interne] = min(candidates, key=len)  # l'en-tête le plus court est le plus précis
                break
    manquantes = [c for c in ("nom", "lat", "lon") if c not in trouvees]
    if manquantes:
        raise ValueError(
            f"Colonnes introuvables dans le CSV DATAtourisme : {manquantes}. "
            f"En-têtes présents : {colonnes}. Compléter EN_TETES dans poi_datatourisme.py."
        )
    return trouvees


def normaliser_poi(brut: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Renvoie la table des POI nettoyée et un bilan (dont les types restés sans thème)."""
    col = reperer_colonnes(list(brut.columns))
    bilan: dict = {"lus": len(brut)}

    def colonne(interne: str) -> pd.Series:
        return brut[col[interne]].str.strip() if interne in col else pd.Series("", index=brut.index)

    poi = pd.DataFrame(
        {
            "nom": colonne("nom"),
            "lat": pd.to_numeric(colonne("lat").str.replace(",", "."), errors="coerce"),
            "lon": pd.to_numeric(colonne("lon").str.replace(",", "."), errors="coerce"),
            "description": colonne("description").str.slice(0, 1500),
            "id": colonne("id"),
            "maj": pd.to_datetime(colonne("maj").str.slice(0, 10), errors="coerce", format="%Y-%m-%d").dt.date,
        }
    )
    poi["types_source"] = colonne("types").apply(lambda v: [nom_local(t) for t in v.split("|") if t.strip()])

    # « 38000#Grenoble » -> code postal + commune
    lieu = colonne("commune").str.split("#", n=1, expand=True)
    if lieu.shape[1] == 2:
        poi["code_postal"], poi["commune"] = lieu[0], lieu[1]
    else:
        poi["code_postal"], poi["commune"] = "", lieu[0]

    # Nettoyage
    valides = poi["lat"].between(-90, 90) & poi["lon"].between(-180, 180) & (poi["nom"] != "")
    bilan["sans_nom_ou_position"] = int((~valides).sum())
    poi = poi[valides]
    lat_min, lat_max, lon_min, lon_max = config.BOITE_REGION
    dans_region = poi["lat"].between(lat_min, lat_max) & poi["lon"].between(lon_min, lon_max)
    bilan["hors_region"] = int((~dans_region).sum())
    poi = poi[dans_region].copy()

    # Identifiant : l'URI DATAtourisme, sinon une empreinte stable du nom et de la position.
    sans_id = poi["id"] == ""
    poi.loc[sans_id, "id"] = poi[sans_id].apply(
        lambda p: "local:" + hashlib.sha1(f"{p['nom']}|{p['lat']:.5f}|{p['lon']:.5f}".encode()).hexdigest()[:16], axis=1
    )
    avant = len(poi)
    poi = poi.drop_duplicates(subset="id").copy()
    bilan["doublons"] = avant - len(poi)

    # Normalisation des thèmes : d'abord par les types, puis par quelques mots du texte.
    poi["themes"] = [
        enrichir_par_texte(classer(types), nom, description)
        for types, nom, description in zip(poi["types_source"], poi["nom"], poi["description"])
    ]
    poi["source"] = SOURCE

    # Types à examiner : ceux des POI restés SANS AUCUN thème (un POI déjà classé n'a pas besoin de plus).
    non_classes = Counter(
        t for types, themes in zip(poi["types_source"], poi["themes"]) if not themes for t in types
        if not est_classe(t) and t.lower() not in TYPES_DATATOURISME  # les équipements de gare sont déjà exploités
    )
    bilan["retenus"] = len(poi)
    bilan["sans_theme"] = int((poi["themes"].str.len() == 0).sum())
    bilan["types_non_classes"] = non_classes.most_common(15)
    return poi[COLONNES].reset_index(drop=True), bilan
