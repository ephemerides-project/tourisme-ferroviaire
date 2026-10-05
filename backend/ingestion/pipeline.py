"""Chaîne d'ingestion complète.

    Sources -> acquisition -> nettoyage -> normalisation -> rapprochement -> stockage

Usages (depuis le dossier backend/) :
    python -m ingestion.pipeline --exemple        # jeu d'essai fictif fourni, hors ligne
    python -m ingestion.pipeline --telecharger    # télécharge les vraies données puis les charge
    python -m ingestion.pipeline                  # recharge les fichiers déjà présents dans donnees/brut/
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import psycopg

from app import config
from ingestion import charger, gares_sncf, gtfs, poi_datatourisme, telecharger


def _premier(dossier: Path, *motifs: str) -> Path:
    for motif in motifs:
        trouves = sorted(dossier.glob(motif))
        if trouves:
            return trouves[0]
    raise FileNotFoundError(f"Aucun fichier {motifs} dans {dossier}. Lancer d'abord avec --telecharger.")


def executer(dossier: Path, journal=print) -> dict:
    debut = time.time()
    chemin_gares = _premier(dossier, "gares-de-voyageurs*.json", "gares-de-voyageurs*.csv")
    chemin_gtfs = _premier(dossier, "gtfs*.zip", "gtfs")
    chemin_poi = _premier(dossier, "datatourisme*.csv")

    journal(f"[1/4] Gares SNCF ({chemin_gares.name})")
    gares, bilan_gares = gares_sncf.normaliser_gares(gares_sncf.lire_gares(chemin_gares))
    journal(f"      {bilan_gares}")
    if gares.empty:
        raise RuntimeError("Aucune gare retenue : vérifier le fichier source et la liste DEPARTEMENTS.")

    journal(f"[2/4] Horaires GTFS ({chemin_gtfs.name})")
    tables = gtfs.lire_gtfs(chemin_gtfs)
    arret_vers_gare, bilan_arrets = gtfs.rattacher_arrets(tables["stops"], gares)
    journal(f"      rattachement arrêts -> gares : {bilan_arrets}")
    liaisons = gtfs.calculer_liaisons(tables, arret_vers_gare, config.TYPES_ROUTE_GTFS)
    journal(f"      {len(liaisons)} liaisons directes entre {liaisons['origine_id'].nunique()} gares")
    if liaisons.empty:
        journal("      ATTENTION : aucune liaison calculée, la recherche par temps de trajet sera vide.")

    journal(f"[3/4] Points d'intérêt DATAtourisme ({chemin_poi.name})")
    poi, bilan_poi = poi_datatourisme.normaliser_poi(poi_datatourisme.lire_csv(chemin_poi))
    types_non_classes = bilan_poi.pop("types_non_classes")
    journal(f"      {bilan_poi}")
    if types_non_classes:
        journal(f"      types sans thème les plus fréquents (à ajouter dans app/themes.py) : {types_non_classes}")

    journal("[4/4] Chargement et rapprochements dans PostgreSQL")
    with psycopg.connect(config.DATABASE_URL) as conn:
        charger.appliquer_schema(conn)
        conn.commit()
        bilan_base = charger.charger(conn, gares, liaisons, poi)
        charger.journaliser(
            conn,
            [
                ("SNCF Open Data", chemin_gares.name, bilan_base["gare"]),
                ("GTFS SNCF", chemin_gtfs.name, bilan_base["liaison"]),
                ("DATAtourisme", chemin_poi.name, bilan_base["poi"]),
            ],
        )
    journal(f"      {bilan_base}")
    journal(f"Terminé en {time.time() - debut:.1f} s.")
    return {"gares": bilan_gares, "arrets": bilan_arrets, "poi": bilan_poi, "base": bilan_base}


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Ingestion des données du projet tourisme ferroviaire")
    parseur.add_argument("--exemple", action="store_true", help="utiliser le jeu d'essai fictif (donnees/exemple)")
    parseur.add_argument("--telecharger", action="store_true", help="télécharger les sources réelles avant de charger")
    parseur.add_argument("--dossier", type=Path, help="dossier contenant les fichiers sources")
    args = parseur.parse_args(argv)

    if args.exemple:
        dossier = config.DOSSIER_DONNEES / "exemple"
        print("Jeu d'essai FICTIF : à utiliser pour développer, jamais pour la démonstration.")
    else:
        dossier = args.dossier or config.DOSSIER_DONNEES / "brut"
        if args.telecharger:
            print("Téléchargement des sources")
            telecharger.telecharger(dossier)
    executer(dossier)
    return 0


if __name__ == "__main__":
    sys.exit(main())
