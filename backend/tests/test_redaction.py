"""Rédaction : gabarits et garde-fous appliqués à la réponse du LLM."""

import pytest

from app.ia import llm, redaction

DESTINATIONS = [
    {
        "gare": {"id": "A", "nom": "Vif"},
        "trajet": {"duree_min": 18, "correspondances": 0, "via": None, "trajets_jour": 2, "duree_estimee": False},
        "nb_pois": 2,
        "pois": [{"nom": "Sentier d'essai", "themes": ["randonnee"], "marche_min": 7}],
    },
    {
        "gare": {"id": "B", "nom": "Annecy"},
        "trajet": {"duree_min": 137, "correspondances": 1, "via": "Grenoble", "trajets_jour": 1, "duree_estimee": True},
        "nb_pois": 1,
        "pois": [{"nom": "Vieille ville d'essai", "themes": ["patrimoine"], "marche_min": 9}],
    },
]


@pytest.mark.parametrize(("minutes", "texte"), [(45, "45 min"), (60, "1 h"), (95, "1 h 35"), (125, "2 h 05")])
def test_duree_lisible(minutes, texte):
    assert redaction.duree_lisible(minutes) == texte


def test_elision():
    assert redaction.de("Grenoble") == "de Grenoble"
    assert redaction.de("Annecy") == "d'Annecy"


def test_justifications_par_gabarit():
    directe = redaction.justification_gabarit(DESTINATIONS[0], "Grenoble")
    assert directe == (
        "18 min de train direct depuis Grenoble. 2 points d'intérêt correspondent à votre demande, "
        "dont « Sentier d'essai » (randonnée) à 7 min à pied de la gare."
    )
    avec_correspondance = redaction.justification_gabarit(DESTINATIONS[1], "Voiron")
    assert "2 h 17 depuis Voiron avec une correspondance à Grenoble (durée estimée)" in avec_correspondance


def test_message_sans_resultat_indique_la_contrainte_a_assouplir():
    aucun_train = redaction.message_sans_resultat({"gares_accessibles": 0}, "Rives", 10, 20, ["culture"])
    assert aucun_train.startswith("Aucune gare n'est accessible en moins de 10 min depuis Rives")
    trop_loin_a_pied = redaction.message_sans_resultat(
        {"gares_accessibles": 12, "marche_min_necessaire": 26, "duree_min_necessaire": 18}, "Grenoble", 120, 20, ["famille"]
    )
    assert "En acceptant 26 min de marche" in trop_loin_a_pied


def test_le_llm_ne_peut_pas_ajouter_de_destination(monkeypatch):
    """Une justification portant sur une gare absente des résultats est jetée."""
    reponse_llm = {
        "introduction": "Voici deux idées.",
        "justifications": {"A": "Vif convient bien.", "Z": "Chamonix est magnifique, départ à 8h12.", "B": 42},
    }
    monkeypatch.setattr(llm, "completer_json", lambda _systeme, _utilisateur: (reponse_llm, {"duree_ms": 1}))
    introduction, justifications, _mesures = redaction.rediger_avec_llm("une randonnée", "Grenoble", DESTINATIONS)
    assert introduction == "Voici deux idées."
    assert justifications == {"A": "Vif convient bien."}  # « Z » inconnue, « B » n'est pas un texte


def test_reponse_llm_sans_introduction_refusee(monkeypatch):
    monkeypatch.setattr(llm, "completer_json", lambda _s, _u: ({"justifications": {}}, {}))
    with pytest.raises(llm.ErreurLLM):
        redaction.rediger_avec_llm("une randonnée", "Grenoble", DESTINATIONS)


def test_le_llm_ne_recoit_que_les_resultats(monkeypatch):
    """Le message envoyé au LLM contient les destinations retenues, et rien d'autre de la base."""
    recu = {}

    def faux_llm(_systeme, utilisateur):
        recu["message"] = utilisateur
        return {"introduction": "ok", "justifications": {}}, {}

    monkeypatch.setattr(llm, "completer_json", faux_llm)
    redaction.rediger_avec_llm("une randonnée", "Grenoble", DESTINATIONS)
    assert "Sentier d'essai" in recu["message"] and "Vieille ville d'essai" in recu["message"]
    assert "trajets_jour" not in recu["message"]
