"""Acquisition : télécharge les fichiers sources dans `donnees/brut/`.

Toutes les sources sont ouvertes et accessibles sans compte ni clé.
Usage : `python -m ingestion.telecharger`
"""

from __future__ import annotations

from pathlib import Path

import requests

from app import config

# nom du fichier local -> (URL, description, licence)
SOURCES: dict[str, tuple[str, str, str]] = {
    "gares-de-voyageurs.json": (
        "https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets/gares-de-voyageurs/exports/json",
        "SNCF Open Data — gares de voyageurs",
        "ODbL",
    ),
    "gtfs-sncf.zip": (
        "https://eu.ftp.opendatasoft.com/sncf/plandata/Export_OpenData_SNCF_GTFS_NewTripId.zip",
        "transport.data.gouv.fr — horaires théoriques SNCF (TGV, Intercités, TER) au format GTFS",
        "ODbL",
    ),
    "datatourisme-reg-ara.csv": (
        "https://www.data.gouv.fr/api/1/datasets/r/5b3c2cee-44b7-48bd-b4e8-439a03ff6cd2",
        "DATAtourisme — points d'intérêt d'Auvergne-Rhône-Alpes (export CSV quotidien)",
        "Licence Ouverte 2.0",
    ),
}


# Sources facultatives : un échec de téléchargement n'empêche pas le chargement du reste.
_SNCF = "https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets"
SOURCES_FACULTATIVES: dict[str, tuple[str, str, str]] = {
    "assistance-pmr.json": (
        f"{_SNCF}/assistance-psh-pmr/exports/json",
        "SNCF Open Data — assistance aux personnes handicapées et à mobilité réduite",
        "voir la fiche du jeu de données",
    ),
    "equipements-accessibilite.json": (
        f"{_SNCF}/equipements-accessibilite-en-gare/exports/json",
        "SNCF Open Data — équipements d'accessibilité en gare",
        "voir la fiche du jeu de données",
    ),
    "ascenseurs.json": (
        f"{_SNCF}/etat-fonctionnement-elevatique-gare/exports/json",
        "SNCF Open Data — état de fonctionnement des ascenseurs et escaliers mécaniques",
        "voir la fiche du jeu de données",
    ),
    "velos-en-gare.json": (
        f"{_SNCF}/stationnement-securise-velo-en-gare-au-30-06-24/exports/json",
        "SNCF Open Data — stationnement vélo sécurisé en gare",
        "voir la fiche du jeu de données",
    ),
    "points-de-vente.json": (
        f"{_SNCF}/points-vente/exports/json",
        "SNCF Open Data — points de vente",
        "voir la fiche du jeu de données",
    ),
    "wifi-en-gare.json": (
        f"{_SNCF}/gares-equipees-du-wifi/exports/json",
        "SNCF Open Data — gares équipées du Wi-Fi",
        "voir la fiche du jeu de données",
    ),
}


def _telecharger_un(url: str, cible: Path) -> None:
    partiel = cible.with_suffix(cible.suffix + ".partiel")
    with requests.get(url, stream=True, timeout=120, headers={"User-Agent": "projet-etudiant-tourisme-ferroviaire"}) as r:
        r.raise_for_status()
        with partiel.open("wb") as f:
            for bloc in r.iter_content(chunk_size=1 << 20):
                f.write(bloc)
    partiel.replace(cible)
    print(f"    -> {cible.name} ({cible.stat().st_size / 1e6:.1f} Mo)")


def telecharger(dossier: Path | None = None, forcer: bool = False) -> Path:
    dossier = dossier or config.DOSSIER_DONNEES / "brut"
    dossier.mkdir(parents=True, exist_ok=True)
    for nom, (url, description, _licence) in SOURCES.items():
        cible = dossier / nom
        if cible.exists() and not forcer:
            print(f"  déjà présent : {nom} ({cible.stat().st_size / 1e6:.1f} Mo)")
            continue
        print(f"  téléchargement : {description}")
        _telecharger_un(url, cible)
    for nom, (url, description, _licence) in SOURCES_FACULTATIVES.items():
        cible = dossier / nom
        if cible.exists() and not forcer:
            print(f"  déjà présent : {nom} ({cible.stat().st_size / 1e6:.1f} Mo)")
            continue
        print(f"  téléchargement : {description}")
        try:
            _telecharger_un(url, cible)
        except requests.RequestException as erreur:
            print(f"    échec, source ignorée : {erreur}")
    return dossier


if __name__ == "__main__":
    telecharger()
