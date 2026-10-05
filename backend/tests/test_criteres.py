"""Validation et mémoire de conversation des critères."""

from app.ia.criteres import Criteres, fusionner


def test_valeurs_inconnues_ecartees():
    """Ce que renverrait un LLM approximatif est nettoyé, pas rejeté en bloc."""
    c = Criteres(origine="  ", duree_max_min="90", marche_max_min=-5, themes=["Nature", "licornes", "nature"], public="seniors", difficulte="FACILE")
    assert c.model_dump() == {
        "origine": None,
        "duree_max_min": 90,
        "marche_max_min": None,
        "themes": ["nature"],
        "public": None,
        "difficulte": "facile",
    }


def test_famille_ajoute_un_theme_de_recherche():
    assert Criteres(themes=["nature"], public="famille").themes_recherches() == ["nature", "famille"]
    assert Criteres(themes=["nature"]).themes_recherches() == ["nature"]


def test_fusion_conserve_le_contexte_et_remplace_les_themes():
    avant = Criteres(origine="Grenoble", duree_max_min=120, themes=["nature", "randonnee"], difficulte="facile")
    apres = fusionner(avant, Criteres(themes=["culture"]))
    assert apres.origine == "Grenoble"
    assert apres.duree_max_min == 120
    assert apres.themes == ["culture"]
    assert apres.difficulte is None  # la difficulté portait sur la randonnée


def test_fusion_sans_contexte():
    nouveaux = Criteres(themes=["culture"])
    assert fusionner(None, nouveaux) == nouveaux
