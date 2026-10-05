"""Rédaction de la réponse : gabarits (toujours disponibles) ou LLM (si configuré).

Dans les deux cas, le texte est produit APRÈS la sélection : il décrit des résultats
déjà choisis par la couche métier. Le LLM ne reçoit que ces résultats et renvoie une
phrase par identifiant de gare ; toute phrase portant sur un autre identifiant est jetée.
"""

from __future__ import annotations

import json

from app.ia import llm
from app.themes import THEMES

CONSIGNE = """Tu rédiges la réponse d'un assistant de tourisme en train.
Tu reçois la demande d'un voyageur et des destinations DÉJÀ sélectionnées et classées par l'application.

Règles strictes :
- Utilise uniquement les informations fournies dans le message.
- Ne cite aucun lieu, horaire, prix, distance ou fait qui n'y figure pas.
- Ne propose aucune autre destination et ne modifie pas l'ordre.
- Écris en français, sobrement, sans superlatifs.

Réponds uniquement par un objet JSON :
{"introduction": "une ou deux phrases",
 "justifications": {"<id de la gare>": "une ou deux phrases expliquant pourquoi cette destination répond à la demande"}}"""

LONGUEUR_MAX = 500


def duree_lisible(minutes: int) -> str:
    """95 -> « 1 h 35 », 45 -> « 45 min », 120 -> « 2 h »."""
    heures, reste = divmod(int(minutes), 60)
    if heures == 0:
        return f"{reste} min"
    return f"{heures} h {reste:02d}" if reste else f"{heures} h"


def de(nom: str) -> str:
    """Élision : « de Grenoble », « d'Annecy »."""
    return f"d'{nom}" if nom[:1].lower() in "aeiouyhéèêàâîôû" else f"de {nom}"


def libelles(themes: list[str]) -> str:
    return ", ".join(THEMES.get(t, t).lower() for t in themes)


def justification_gabarit(destination: dict, origine: str) -> str:
    """Phrase construite uniquement à partir des données de la destination."""
    trajet = destination["trajet"]
    if trajet["correspondances"]:
        acces = f"{duree_lisible(trajet['duree_min'])} depuis {origine} avec une correspondance à {trajet['via']} (durée estimée)"
    else:
        acces = f"{duree_lisible(trajet['duree_min'])} de train direct depuis {origine}"
    premier = destination["pois"][0]
    nb = destination["nb_pois"]
    offre = "1 point d'intérêt correspond" if nb == 1 else f"{nb} points d'intérêt correspondent"
    return (
        f"{acces}. {offre} à votre demande, dont « {premier['nom']} » "
        f"({libelles(premier['themes'])}) à {premier['marche_min']} min à pied de la gare."
    )


def introduction_gabarit(nb: int, origine: str, duree_max: int, themes: list[str]) -> str:
    quoi = f" pour : {libelles(themes)}" if themes else ""
    pluriel = "s" if nb > 1 else ""
    return f"{nb} destination{pluriel} à moins de {duree_lisible(duree_max)} {de(origine)}{quoi}."


def message_sans_resultat(diagnostic: dict, origine: str, duree_max: int, marche_max: int, themes: list[str]) -> str:
    """Quand rien ne correspond : on le dit, et on indique quelle contrainte assouplir."""
    if diagnostic["gares_accessibles"] == 0:
        return (
            f"Aucune gare n'est accessible en moins de {duree_lisible(duree_max)} depuis {origine} "
            "dans les données chargées. Essayez avec un temps de trajet plus long."
        )
    quoi = f" « {libelles(themes)} »" if themes else ""
    nb = diagnostic["gares_accessibles"]
    debut = "1 gare est accessible" if nb == 1 else f"{nb} gares sont accessibles"
    suite = "mais elle n'a pas" if nb == 1 else "mais aucune n'a"
    message = (
        f"{debut} en moins de {duree_lisible(duree_max)} depuis {origine}, "
        f"{suite} de point d'intérêt{quoi} à moins de {marche_max} min à pied."
    )
    if diagnostic.get("marche_min_necessaire"):
        return message + f" En acceptant {diagnostic['marche_min_necessaire']} min de marche, il y aurait des résultats."
    if diagnostic.get("duree_min_necessaire"):
        return message + (
            f" La destination correspondante la plus proche est à {duree_lisible(diagnostic['duree_min_necessaire'])} de train."
        )
    return message + " Les données chargées ne contiennent aucun point d'intérêt de ce type près d'une gare."


def rediger_avec_llm(question: str, origine: str, destinations: list[dict]) -> tuple[str, dict[str, str], dict]:
    """Renvoie (introduction, justifications par id de gare, mesures). Lève ErreurLLM en cas d'échec."""
    donnees = {
        "demande": question,
        "depart": origine,
        "destinations": [
            {
                "id": d["gare"]["id"],
                "gare": d["gare"]["nom"],
                "duree_trajet_min": d["trajet"]["duree_min"],
                "correspondances": d["trajet"]["correspondances"],
                "correspondance_a": d["trajet"]["via"],
                "points_interet": [
                    {"nom": p["nom"], "themes": p["themes"], "marche_depuis_la_gare_min": p["marche_min"]} for p in d["pois"]
                ],
            }
            for d in destinations
        ],
    }
    objet, mesures = llm.completer_json(CONSIGNE, json.dumps(donnees, ensure_ascii=False))

    introduction = objet.get("introduction")
    if not isinstance(introduction, str) or not introduction.strip():
        raise llm.ErreurLLM("Introduction absente de la réponse du LLM")
    ids_connus = {d["gare"]["id"] for d in destinations}
    brutes = objet.get("justifications") if isinstance(objet.get("justifications"), dict) else {}
    justifications = {
        str(gare_id): texte.strip()[:LONGUEUR_MAX]
        for gare_id, texte in brutes.items()
        if str(gare_id) in ids_connus and isinstance(texte, str) and texte.strip()
    }
    return introduction.strip()[:LONGUEUR_MAX], justifications, mesures
