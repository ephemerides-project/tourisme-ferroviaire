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


def telecharger(dossier: Path | None = None, forcer: bool = False) -> Path:
    dossier = dossier or config.DOSSIER_DONNEES / "brut"
    dossier.mkdir(parents=True, exist_ok=True)
    for nom, (url, description, _licence) in SOURCES.items():
        cible = dossier / nom
        if cible.exists() and not forcer:
            print(f"  déjà présent : {nom} ({cible.stat().st_size / 1e6:.1f} Mo)")
            continue
        print(f"  téléchargement : {description}")
        partiel = cible.with_suffix(cible.suffix + ".partiel")
        with requests.get(url, stream=True, timeout=120, headers={"User-Agent": "projet-etudiant-tourisme-ferroviaire"}) as r:
            r.raise_for_status()
            with partiel.open("wb") as f:
                for bloc in r.iter_content(chunk_size=1 << 20):
                    f.write(bloc)
        partiel.replace(cible)
        print(f"    -> {nom} ({cible.stat().st_size / 1e6:.1f} Mo)")
    return dossier


if __name__ == "__main__":
    telecharger()
