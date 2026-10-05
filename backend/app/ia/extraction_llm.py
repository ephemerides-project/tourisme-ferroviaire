"""Extraction des critères AVEC LLM.

Le LLM a un seul travail ici : traduire une phrase en critères structurés.
Il ne propose aucune destination et ne connaît aucune donnée de la base.
"""

from __future__ import annotations

from app.ia import llm
from app.ia.criteres import Criteres
from app.themes import THEMES

CONSIGNE = f"""Tu extrais des critères de recherche à partir de la demande d'un voyageur en train.
Réponds uniquement par un objet JSON avec exactement ces clés :

- "origine" : ville ou gare de départ citée par l'utilisateur, sinon null
- "duree_max_min" : temps de trajet maximal en train, en minutes (entier), sinon null
- "marche_max_min" : temps de marche maximal depuis la gare, en minutes (entier), sinon null
- "themes" : liste de thèmes choisis UNIQUEMENT parmi {list(THEMES)} ; liste vide si aucun ne correspond
- "public" : "famille" si des enfants sont du voyage, sinon null
- "difficulte" : "facile", "moyen" ou "difficile" si un niveau est exprimé, sinon null

Règles :
- N'invente rien : une information absente de la demande vaut null ou une liste vide.
- Ne propose jamais de destination, de lieu ou d'horaire.
- "1h30" vaut 90, "une demi-heure" vaut 30.
- Une durée liée à la marche ou à « à pied » va dans "marche_max_min", jamais dans "duree_max_min".

Exemple
Demande : "Je cherche une sortie nature à moins de 1h30 de Grenoble avec une randonnée facile près de la gare."
Réponse : {{"origine": "Grenoble", "duree_max_min": 90, "marche_max_min": null, "themes": ["nature", "randonnee"], "public": null, "difficulte": "facile"}}"""


def extraire(question: str) -> tuple[Criteres, dict]:
    """Renvoie (critères validés, mesures d'usage). Lève ErreurLLM si le LLM est inutilisable."""
    objet, mesures = llm.completer_json(CONSIGNE, question)
    # Le modèle Criteres écarte tout thème inconnu et toute valeur hors bornes.
    return Criteres(**{champ: objet.get(champ) for champ in Criteres.model_fields}), mesures
