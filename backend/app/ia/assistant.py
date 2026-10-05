"""Assistant « Demander » : orchestre la chaîne complète.

    question -> critères (LLM ou règles) -> fusion avec la conversation
             -> recherche et classement en base (couche métier)
             -> rédaction (LLM ou gabarits) -> réponse structurée

Le LLM n'apparaît qu'aux deux extrémités. S'il est absent ou en panne, tout fonctionne quand même.
"""

from __future__ import annotations

import re
import time

import psycopg

from app import config
from app.ia import extraction_llm, extraction_regles, llm, redaction
from app.ia.criteres import Criteres, fusionner
from app.metier import destinations as metier_destinations
from app.metier import gares as metier_gares
from app.texte import normaliser
from app.themes import THEMES_ACTIVITE

# « Que faire autour de cette gare ? » : la gare sélectionnée sur la carte est la destination, pas le départ.
MOTIF_AUTOUR = re.compile(r"\b(cette gare|autour|ici|sur place|a proximite|a cote)\b")


def repondre(
    conn: psycopg.Connection,
    question: str,
    contexte: Criteres | None = None,
    gare_selectionnee: str | None = None,
    utiliser_llm: bool = True,
) -> dict:
    debut = time.perf_counter()
    avertissements: list[str] = []
    mesures: dict = {}

    # 1. Compréhension de la demande.
    nouveaux, moteur_extraction = _extraire(conn, question, utiliser_llm, avertissements, mesures)
    criteres = fusionner(contexte, nouveaux)
    themes = criteres.themes_recherches()
    marche_max = criteres.marche_max_min or config.MARCHE_MAX_PAR_DEFAUT_MIN
    duree_max = criteres.duree_max_min or config.DUREE_MAX_PAR_DEFAUT_MIN
    par_defaut = [
        champ
        for champ, valeur in (("duree_max_min", criteres.duree_max_min), ("marche_max_min", criteres.marche_max_min))
        if valeur is None
    ]
    if criteres.difficulte:
        avertissements.append(
            f"Le niveau de difficulté demandé (« {criteres.difficulte} ») n'est pas renseigné "
            "dans les données actuelles : il n'a pas été pris en compte."
        )

    if "evenement" in themes:
        avertissements.append("Les dates des événements ne sont pas contrôlées : vérifiez qu'ils ont bien lieu.")

    reponse = {
        "question": question,
        "criteres": criteres.model_dump(),  # à renvoyer tel quel dans `contexte` au message suivant
        "criteres_appliques": {
            "themes": themes,
            "duree_max_min": duree_max,
            "marche_max_min": marche_max,
            "valeurs_par_defaut": par_defaut,
        },
        "mode": "destinations",
        "origine": None,
        "destinations": [],
        "introduction": "",
        "avertissements": avertissements,
        "moteur": {"extraction": moteur_extraction, "redaction": "gabarit"},
        "mesures": mesures,
    }

    # 2a. Cas « autour de la gare sélectionnée sur la carte ».
    gare_carte = metier_gares.trouver_gare(conn, gare_selectionnee) if gare_selectionnee else None
    if gare_carte and nouveaux.origine is None and MOTIF_AUTOUR.search(normaliser(question)):
        _autour_de(conn, reponse, gare_carte, themes, marche_max)
        return _terminer(reponse, debut)

    # 2b. Cas général : d'où part-on ?
    if criteres.origine:
        origine = metier_gares.resoudre_gare(conn, criteres.origine)
        if origine is None:
            reponse["introduction"] = (
                f"Je ne trouve pas de gare correspondant à « {criteres.origine} » dans les données chargées. "
                "Précisez une ville de départ desservie par le train dans la région."
            )
            return _terminer(reponse, debut)
    elif gare_carte:
        origine = {k: gare_carte[k] for k in ("id", "nom", "lat", "lon")}
    else:
        origine = metier_gares.resoudre_gare(conn, config.ORIGINE_PAR_DEFAUT)
        if origine is None:
            reponse["introduction"] = "Indiquez une ville de départ pour lancer la recherche."
            return _terminer(reponse, debut)
        avertissements.append(f"Ville de départ non précisée : {origine['nom']} utilisée par défaut.")
        par_defaut.append("origine")
    reponse["origine"] = origine

    # 3. Recherche et classement : couche métier, sans LLM.
    resultats, diagnostic = metier_destinations.rechercher(
        conn, origine["id"], duree_max, themes, marche_max, config.NB_RECOMMANDATIONS
    )
    reponse["diagnostic"] = diagnostic
    if not resultats:
        reponse["introduction"] = redaction.message_sans_resultat(diagnostic, origine["nom"], duree_max, marche_max, themes)
        return _terminer(reponse, debut)
    if any(d["trajet"]["duree_estimee"] for d in resultats):
        avertissements.append("Les durées des trajets avec correspondance sont des estimations.")

    # 4. Rédaction : gabarits par défaut, remplacés par le LLM s'il répond correctement.
    reponse["introduction"] = redaction.introduction_gabarit(len(resultats), origine["nom"], duree_max, themes)
    for destination in resultats:
        destination["justification"] = redaction.justification_gabarit(destination, origine["nom"])
    if utiliser_llm and llm.disponible():
        try:
            introduction, justifications, mesures["redaction"] = redaction.rediger_avec_llm(question, origine["nom"], resultats)
            reponse["introduction"] = introduction
            for destination in resultats:
                destination["justification"] = justifications.get(destination["gare"]["id"], destination["justification"])
            reponse["moteur"]["redaction"] = "llm"
        except llm.ErreurLLM as erreur:
            mesures["erreur_redaction"] = str(erreur)
    reponse["destinations"] = resultats
    return _terminer(reponse, debut)


def _extraire(conn, question: str, utiliser_llm: bool, avertissements: list[str], mesures: dict) -> tuple[Criteres, str]:
    """Extraction par LLM si possible, sinon par règles. Renvoie (critères, moteur utilisé)."""
    if utiliser_llm and llm.disponible():
        try:
            criteres, mesures["extraction"] = extraction_llm.extraire(question)
            return criteres, "llm"
        except llm.ErreurLLM as erreur:
            mesures["erreur_extraction"] = str(erreur)
            avertissements.append("Assistant IA momentanément indisponible : demande analysée par règles.")
    noms_gares = [g["nom"] for g in conn.execute("SELECT nom FROM gare WHERE desservie").fetchall()]
    return extraction_regles.extraire(question, noms_gares), "regles"


def _autour_de(conn, reponse: dict, gare: dict, themes: list[str], marche_max: int) -> None:
    """Remplit la réponse avec les points d'intérêt proches de la gare sélectionnée."""
    pois = metier_gares.poi_proches(conn, gare["id"], themes or list(THEMES_ACTIVITE), marche_max)
    reponse["mode"] = "autour"
    reponse["origine"] = {k: gare[k] for k in ("id", "nom", "lat", "lon")}
    quoi = f" « {redaction.libelles(themes)} »" if themes else ""
    if not pois:
        reponse["introduction"] = (
            f"Aucun point d'intérêt{quoi} à moins de {marche_max} min à pied de la gare {redaction.de(gare['nom'])} "
            "dans les données chargées."
        )
        return
    pluriel = "s" if len(pois) > 1 else ""
    reponse["introduction"] = (
        f"{len(pois)} point{pluriel} d'intérêt{quoi} à moins de {marche_max} min à pied de la gare {redaction.de(gare['nom'])}."
    )
    reponse["destinations"] = [
        {
            "gare": reponse["origine"],
            "trajet": None,
            "score": None,
            "detail_score": None,
            "nb_pois": len(pois),
            "pois": pois[:10],
            "justification": f"Le plus proche : « {pois[0]['nom']} », à {pois[0]['marche_min']} min à pied.",
        }
    ]


def _terminer(reponse: dict, debut: float) -> dict:
    reponse["mesures"]["duree_totale_ms"] = round((time.perf_counter() - debut) * 1000)
    return reponse
