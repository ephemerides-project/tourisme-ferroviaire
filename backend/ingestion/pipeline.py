"""Chaîne d'ingestion complète.

    Sources -> acquisition -> nettoyage -> normalisation -> rapprochement -> stockage

Usages (depuis le dossier backend/) :
    python -m ingestion.pipeline --exemple        # jeu d'essai fictif fourni, hors ligne
    python -m ingestion.pipeline --telecharger    # télécharge les vraies données puis les charge
    python -m ingestion.pipeline                  # recharge les fichiers déjà présents dans donnees/brut/
    python -m ingestion.pipeline --voies          # idem, en téléchargeant d'abord le tracé des lignes (SNCF Open Data)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import psycopg
import requests

from app import config
from ingestion import charger, gares_sncf, gtfs, poi_datatourisme, services, telecharger, voies


def _premier(dossier: Path, *motifs: str) -> Path:
    for motif in motifs:
        trouves = sorted(dossier.glob(motif))
        if trouves:
            return trouves[0]
    raise FileNotFoundError(f"Aucun fichier {motifs} dans {dossier}. Lancer d'abord avec --telecharger.")


def executer(dossier: Path, journal=print, telecharger_voies: bool = False) -> dict:
    debut = time.time()
    # Le schéma d'abord : une base injoignable échoue tout de suite, et non après la lecture des fichiers.
    with psycopg.connect(config.DATABASE_URL) as conn:
        charger.appliquer_schema(conn)

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
    services_gares, bilan_services = services.rassembler(dossier, gares, tables, arret_vers_gare)
    journal(f"      services en gare (nombre de gares par service) : {bilan_services}")
    del tables  # les horaires ne servent plus : on libère la mémoire
    liaisons["trace"], bilan_voies = _suivre_les_voies(dossier, gares, liaisons["trace"].tolist(), telecharger_voies, journal)

    journal(f"[3/4] Points d'intérêt DATAtourisme ({chemin_poi.name})")
    poi, bilan_poi = poi_datatourisme.normaliser_poi(poi_datatourisme.lire_csv(chemin_poi))
    types_non_classes = bilan_poi.pop("types_non_classes")
    journal(f"      {bilan_poi}")
    if types_non_classes:
        journal(f"      types sans thème les plus fréquents (à ajouter dans app/themes.py) : {types_non_classes}")

    journal("[4/4] Chargement et rapprochements dans PostgreSQL")
    with psycopg.connect(config.DATABASE_URL) as conn:
        bilan_base = charger.charger(conn, gares, liaisons, poi, services_gares)
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
    return {"gares": bilan_gares, "arrets": bilan_arrets, "voies": bilan_voies, "services": bilan_services, "poi": bilan_poi, "base": bilan_base}


def _suivre_les_voies(dossier: Path, gares, traces: list, telecharger_voies: bool, journal) -> tuple[list, dict]:
    """Étape facultative : fait passer les tracés par les voies ferrées.

    Source par défaut : les lignes SNCF (`lignes-sncf.geojson`). À défaut, les voies
    d'OpenStreetMap (`voies-osm.json`). Sans aucun des deux fichiers, les tracés restent tels quels.
    """
    chemin_sncf, chemin_osm = dossier / "lignes-sncf.geojson", dossier / "voies-osm.json"
    if telecharger_voies:
        try:
            voies.telecharger_lignes_sncf(chemin_sncf)
        except requests.RequestException as erreur:
            journal(f"      ATTENTION : téléchargement des lignes SNCF impossible ({erreur})")
    chemin_voies = chemin_sncf if chemin_sncf.exists() else chemin_osm
    if not chemin_voies.exists():
        journal("      pas de fichier de voies : tracés en segments droits entre arrêts (voir l'option --voies)")
        return traces, {}
    try:
        reseau = voies.lire_lignes_sncf(chemin_voies, gares) if chemin_voies == chemin_sncf else voies.lire(chemin_voies)
    except ValueError as erreur:  # fichier tronqué, ou page d'erreur à la place du JSON
        journal(f"      ATTENTION : {chemin_voies.name} est illisible ({erreur}). Le supprimer puis relancer avec --voies.")
        return traces, {}
    if reseau.remarque or not reseau.positions:
        journal(f"      ATTENTION : fichier de voies incomplet ({reseau.remarque or 'aucune voie'}). Supprimer {chemin_voies.name} puis relancer avec --voies.")
    traces, bilan = voies.suivre(traces, reseau)
    bilan["noeuds_du_reseau"] = len(reseau.positions)
    journal(f"      tracés le long des voies ({chemin_voies.name}) : {bilan}")
    if bilan["sur_les_voies"] < bilan["troncons"]:
        journal("      les tronçons restants gardent un segment droit (arrêt loin des voies, ou hors de la zone).")
    return traces, bilan


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Ingestion des données du projet tourisme ferroviaire")
    parseur.add_argument("--exemple", action="store_true", help="utiliser le jeu d'essai fictif (donnees/exemple)")
    parseur.add_argument("--telecharger", action="store_true", help="télécharger les sources réelles avant de charger")
    parseur.add_argument("--voies", action="store_true", help="télécharger le tracé des lignes SNCF (une fois)")
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
    executer(dossier, telecharger_voies=args.voies and not args.exemple)
    return 0


if __name__ == "__main__":
    sys.exit(main())
