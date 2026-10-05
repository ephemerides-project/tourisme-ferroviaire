"""Extraction des critères sans LLM, sur les requêtes données dans le sujet."""

import pytest

from app.ia.extraction_regles import extraire

GARES = ["Grenoble", "Grenoble-Universités-Gières", "Chambéry-Challes-les-Eaux", "Lyon Part-Dieu", "Les Arcs", "Voiron"]


def criteres(question: str) -> dict:
    """Critères extraits, limités aux champs renseignés."""
    return {champ: valeur for champ, valeur in extraire(question, GARES).model_dump().items() if valeur}


def test_requete_complete_du_sujet():
    question = (
        "Je cherche une sortie nature à moins de 1h30 de Grenoble, avec une randonnée facile "
        "et moins de 20 minutes de marche depuis la gare."
    )
    assert criteres(question) == {
        "origine": "Grenoble",
        "duree_max_min": 90,
        "marche_max_min": 20,
        "themes": ["nature", "randonnee"],
        "difficulte": "facile",
    }


def test_enfants_et_montagne():
    question = (
        "Je voudrais passer une journée à la montagne sans voiture, à moins de 2 heures de Grenoble, "
        "avec une activité adaptée à des enfants."
    )
    assert criteres(question) == {"origine": "Grenoble", "duree_max_min": 120, "themes": ["montagne"], "public": "famille"}


@pytest.mark.parametrize(
    ("question", "trajet", "marche"),
    [
        ("Je cherche une activité à moins d'une heure de Grenoble.", 60, None),
        ("Je ne veux pas marcher plus de 15 minutes après la gare.", None, 15),
        ("moins de 2 heures de train, une activité nature et moins de 20 minutes de marche", 120, 20),
        ("une baignade à moins de 10 minutes de marche, 1h30 max depuis Grenoble", 90, 10),
        ("1h max, 10 min à pied", 60, 10),
        ("un musée à une heure et demie de Lyon", 90, None),
        ("à une demi-heure de Voiron", 30, None),
        ("pas de durée ici", None, None),
    ],
)
def test_durees_de_trajet_et_de_marche(question, trajet, marche):
    extrait = extraire(question, GARES)
    assert (extrait.duree_max_min, extrait.marche_max_min) == (trajet, marche)


@pytest.mark.parametrize(
    ("question", "origine"),
    [
        ("à moins de 1h30 de Grenoble", "Grenoble"),
        ("1h max depuis chambéry", "Chambery"),  # sans majuscule : reconnu grâce au nom de gare
        ("un musée à une heure de Lyon", "Lyon"),
        ("une randonnée depuis Clermont-Ferrand", "Clermont-Ferrand"),  # gare inconnue : renvoyée telle quelle
        ("moins de 20 minutes de marche depuis la gare", None),
        ("Que faire avec les enfants ?", None),  # « les » ne doit pas désigner la gare « Les Arcs »
    ],
)
def test_origine(question, origine):
    assert extraire(question, GARES).origine == origine


def test_question_de_suivi_ne_contient_que_le_theme():
    assert criteres("Et si je préfère finalement quelque chose de culturel ?") == {"themes": ["culture"]}
