"""Évaluation de l'assistant sur un jeu de requêtes (section 17 du sujet).

Pour chaque requête, on mesure :
- la compréhension : les critères extraits sont-ils ceux attendus ?
- le respect des contraintes : chaque résultat tient-il dans le temps de trajet et de marche demandés,
  avec au moins un thème demandé ? (vérifié automatiquement à partir de la réponse)
- le moteur réellement utilisé : le LLM a-t-il répondu, ou a-t-on basculé sur les règles ?
- le nombre de résultats, le temps de réponse et les jetons consommés.

Usage (depuis backend/, base chargée) :
    python -m evaluation.evaluer              # avec le LLM configuré, sinon par règles
    python -m evaluation.evaluer --sans-llm   # extraction par règles : sert de point de comparaison
    python -m evaluation.evaluer --serie nouvelles   # une seule série (utile quand le LLM est lent)
    python -m evaluation.evaluer --csv resultats.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app import config
from app.ia import assistant
from app.ia.criteres import Criteres
from app.texte import normaliser

REQUETES = Path(__file__).with_name("requetes.json")


def ecarts_de_criteres(obtenus: dict, attendus: dict) -> list[str]:
    """Liste des critères qui diffèrent de l'attendu (vide si tout est conforme).

    - l'origine est comparée sans accents ni majuscules (« Chambery » = « Chambéry ») ;
    - les thèmes sont comparés tels qu'ils seront recherchés : dire « famille » dans `public`
      ou dans `themes` revient au même, on ne le compte donc pas comme un écart.
    """
    obtenu, attendu = Criteres(**obtenus), Criteres(**attendus)
    ecarts = []
    if normaliser(obtenu.origine or "") != normaliser(attendu.origine or ""):
        ecarts.append(f"origine : obtenu {obtenu.origine!r}, attendu {attendu.origine!r}")
    for champ in ("duree_max_min", "marche_max_min", "difficulte"):
        if getattr(obtenu, champ) != getattr(attendu, champ):
            ecarts.append(f"{champ} : obtenu {getattr(obtenu, champ)!r}, attendu {getattr(attendu, champ)!r}")
    if sorted(obtenu.themes_recherches()) != sorted(attendu.themes_recherches()):
        ecarts.append(f"themes : obtenu {sorted(obtenu.themes_recherches())}, attendu {sorted(attendu.themes_recherches())}")
    return ecarts


def contraintes_respectees(reponse: dict) -> bool:
    """Vérifie chaque destination proposée par rapport aux critères réellement appliqués."""
    appliques = reponse["criteres_appliques"]
    for destination in reponse["destinations"]:
        if destination["trajet"] and destination["trajet"]["duree_min"] > appliques["duree_max_min"]:
            return False
        for poi in destination["pois"]:
            if poi["marche_min"] > appliques["marche_max_min"]:
                return False
            if appliques["themes"] and not set(poi["themes"]) & set(appliques["themes"]):
                return False
    return True


def evaluer(utiliser_llm: bool, serie: str | None = None) -> list[dict]:
    requetes = json.loads(REQUETES.read_text(encoding="utf-8"))
    if serie:
        requetes = [r for r in requetes if r.get("serie") == serie]
    lignes = []
    with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as conn:
        for requete in requetes:
            reponse = assistant.repondre(conn, requete["question"], utiliser_llm=utiliser_llm)
            mesures = reponse["mesures"]
            appels = [mesures.get(etape) or {} for etape in ("extraction", "redaction")]
            ecarts = ecarts_de_criteres(reponse["criteres"], requete["attendu"])
            lignes.append(
                {
                    "question": requete["question"],
                    "serie": requete.get("serie", ""),
                    "extraction": reponse["moteur"]["extraction"],
                    "redaction": reponse["moteur"]["redaction"],
                    "criteres_ok": not ecarts,
                    "contraintes_ok": contraintes_respectees(reponse),
                    "nb_resultats": len(reponse["destinations"]),
                    "duree_ms": mesures["duree_totale_ms"],
                    "duree_extraction_llm_ms": appels[0].get("duree_ms"),
                    "duree_redaction_llm_ms": appels[1].get("duree_ms"),
                    "jetons_entree": sum(a.get("jetons_entree") or 0 for a in appels),
                    "jetons_sortie": sum(a.get("jetons_sortie") or 0 for a in appels),
                    "ecarts": " ; ".join(ecarts),
                    "erreur_extraction": mesures.get("erreur_extraction", ""),
                    "erreur_redaction": mesures.get("erreur_redaction", ""),
                }
            )
    return lignes


def afficher(lignes: list[dict], llm_demande: bool) -> None:
    print(f"{'critères':9}{'contraintes':12}{'extraction':11}{'rédaction':10}{'résultats':10}{'ms':>7}  question")
    for ligne in lignes:
        print(
            f"{'ok' if ligne['criteres_ok'] else 'ÉCART':9}{'ok' if ligne['contraintes_ok'] else 'ÉCART':12}"
            f"{ligne['extraction']:11}{ligne['redaction']:10}{ligne['nb_resultats']:<10}{ligne['duree_ms']:>7}  "
            f"{ligne['question'][:60]}"
        )

    nb = len(lignes)
    durees = sorted(ligne["duree_ms"] for ligne in lignes)
    print(
        f"\nCritères conformes : {sum(l['criteres_ok'] for l in lignes)}/{nb} | "
        f"contraintes respectées : {sum(l['contraintes_ok'] for l in lignes)}/{nb} | "
        f"temps médian : {durees[nb // 2]} ms | "
        f"jetons : {sum(l['jetons_entree'] for l in lignes)} en entrée, {sum(l['jetons_sortie'] for l in lignes)} en sortie"
    )
    for serie in dict.fromkeys(ligne["serie"] for ligne in lignes if ligne["serie"]):
        de_la_serie = [ligne for ligne in lignes if ligne["serie"] == serie]
        print(f"  série « {serie} » : critères conformes {sum(l['criteres_ok'] for l in de_la_serie)}/{len(de_la_serie)}")
    if llm_demande:
        # Sans ces deux lignes, un LLM qui échoue passe inaperçu : le repli sur les règles donne de bons critères.
        print(
            f"Extraction faite par le LLM : {sum(l['extraction'] == 'llm' for l in lignes)}/{nb} "
            f"(les autres : repli sur les règles) | "
            f"rédaction faite par le LLM : {sum(l['redaction'] == 'llm' for l in lignes)}/{nb}"
        )
        erreurs = Counter(
            f"{etape} : {ligne[cle]}"
            for ligne in lignes
            for etape, cle in (("extraction", "erreur_extraction"), ("rédaction", "erreur_redaction"))
            if ligne[cle]
        )
        for erreur, occurrences in erreurs.most_common():
            print(f"  échec LLM x{occurrences} — {erreur[:300]}")

    avec_ecart = [ligne for ligne in lignes if not ligne["criteres_ok"]]
    if avec_ecart:
        print("\nDétail des écarts de critères :")
        for ligne in avec_ecart:
            print(f"  [{ligne['extraction']}] {ligne['question'][:90]}")
            print(f"      {ligne['ecarts']}")


def main() -> None:
    parseur = argparse.ArgumentParser(description="Évalue l'assistant sur les requêtes de evaluation/requetes.json")
    parseur.add_argument("--sans-llm", action="store_true", help="forcer l'extraction par règles")
    parseur.add_argument("--csv", type=Path, help="écrire aussi le détail dans ce fichier CSV")
    parseur.add_argument("--serie", help="ne rejouer qu'une série de requêtes (« sujet » ou « nouvelles »)")
    args = parseur.parse_args()

    from app.ia import llm

    llm_demande = not args.sans_llm and llm.disponible()
    if not args.sans_llm and not llm.disponible():
        print("Aucun LLM configuré (LLM_BASE_URL / LLM_MODEL) : évaluation des règles seules.\n")
    else:
        print(f"Moteur évalué : {'LLM ' + config.LLM_MODEL + ' (délai ' + str(int(config.LLM_TIMEOUT_S)) + ' s)' if llm_demande else 'règles'}\n")

    lignes = evaluer(utiliser_llm=llm_demande, serie=args.serie)
    if not lignes:
        print(f"Aucune requête dans la série « {args.serie} ».")
        return
    afficher(lignes, llm_demande)
    if args.csv:
        with args.csv.open("w", newline="", encoding="utf-8") as f:
            ecrivain = csv.DictWriter(f, fieldnames=list(lignes[0]))
            ecrivain.writeheader()
            ecrivain.writerows(lignes)
        print(f"\nDétail écrit dans {args.csv}")


if __name__ == "__main__":
    main()
