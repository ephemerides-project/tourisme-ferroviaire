"""Chaîne complète sur le jeu d'essai : base -> couche métier -> API -> assistant.

Ces tests ont besoin de la base de test (variable DATABASE_URL_TEST), voir conftest.py.
"""

import pytest
from fastapi.testclient import TestClient

from app import config
from app.ia import llm
from app.main import app

pytestmark = [pytest.mark.base, pytest.mark.usefixtures("base_chargee", "sans_llm")]

GRENOBLE, VIF, VOIRON, CHAMBERY, ANNECY, MONESTIER = "87747006", "87747139", "87747337", "87741009", "87746008", "87747154"
QUESTION_SUJET = (
    "Je cherche une sortie nature à moins de 1h30 de Grenoble, avec une randonnée facile "
    "et moins de 20 minutes de marche depuis la gare."
)


@pytest.fixture()
def client():
    return TestClient(app)


def demander(client, question, **options) -> dict:
    reponse = client.post("/recherche", json={"question": question, **options})
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


# --- Chargement -----------------------------------------------------------------
def test_volumes_charges(client, base_chargee):
    volumes = client.get("/stats").json()["volumes"]
    assert volumes == {
        "gares": 13,
        "gares_desservies": 13,
        "liaisons_directes": 66,
        "trajets_avec_correspondance": 90,
        "points_interet": 28,
        "rattachements_gare_poi": 27,  # 28 POI, dont un à 3,2 km de toute gare
    }
    assert base_chargee["base"]["gare_uic"] == 14  # Grenoble porte deux codes UIC


def test_marche_estimee(conn):
    """400 m à vol d'oiseau x 1,3 de détour / 75 m par minute = 6,9 -> 7 min."""
    ligne = conn.execute(
        "SELECT gp.distance_m, gp.marche_min FROM gare_poi gp JOIN poi p ON p.id = gp.poi_id WHERE p.nom = %s",
        ("Sentier d'essai des Coteaux",),
    ).fetchone()
    assert abs(ligne["distance_m"] - 400) <= 2
    assert ligne["marche_min"] == 7


def test_correspondance_estimee(conn):
    """Voiron -> Chambéry : pas de direct, 18 min + 54 min + 15 min de marge via Grenoble."""
    ligne = conn.execute(
        "SELECT duree_min, correspondances, via_id FROM accessibilite WHERE origine_id = %s AND destination_id = %s",
        (VOIRON, CHAMBERY),
    ).fetchone()
    assert ligne == {"duree_min": 87, "correspondances": 1, "via_id": GRENOBLE}


# --- Explorer -------------------------------------------------------------------
def test_recherche_de_gare_sans_accent(client):
    gares = client.get("/gares", params={"q": "chambery"}).json()
    assert [g["nom"] for g in gares] == ["Chambéry-Challes-les-Eaux"]
    assert gares[0]["nb_poi"] == 4


def test_poi_proches_filtres(client):
    tous = client.get(f"/gares/{VIF}/poi").json()
    assert [p["nom"] for p in tous] == ["Sentier d'essai des Coteaux", "Belvédère d'essai du Drac", "Ferme pédagogique d'essai"]
    proches = client.get(f"/gares/{VIF}/poi", params={"theme": "randonnee", "marche_max": 20}).json()
    assert [p["nom"] for p in proches] == ["Sentier d'essai des Coteaux"]


def test_erreurs_explicites(client):
    assert client.get("/gares/inconnue/poi").status_code == 404
    assert client.get("/destinations", params={"origine": "Atlantide"}).status_code == 404
    assert client.get("/destinations", params={"origine": "Grenoble", "theme": "licornes"}).status_code == 422


def test_destinations_respectent_les_contraintes(client):
    corps = client.get(
        "/destinations", params={"origine": "Grenoble", "duree_max": 90, "marche_max": 20, "theme": ["randonnee", "nature"]}
    ).json()
    destinations = corps["destinations"]
    assert corps["origine"]["id"] == GRENOBLE
    assert destinations[0]["gare"]["id"] == VIF  # la seule à couvrir les deux thèmes
    assert [d["score"] for d in destinations] == sorted((d["score"] for d in destinations), reverse=True)
    for d in destinations:
        assert d["trajet"]["duree_min"] <= 90
        assert d["gare"]["id"] != GRENOBLE
        for poi in d["pois"]:
            assert poi["marche_min"] <= 20
            assert set(poi["themes"]) & {"randonnee", "nature"}


# --- Demander ---------------------------------------------------------------------
def test_question_du_sujet(client):
    reponse = demander(client, QUESTION_SUJET)
    assert reponse["moteur"] == {"extraction": "regles", "redaction": "gabarit"}
    assert reponse["origine"]["id"] == GRENOBLE
    assert reponse["criteres_appliques"] == {
        "themes": ["nature", "randonnee"], "duree_max_min": 90, "marche_max_min": 20, "valeurs_par_defaut": [],
    }
    premiere = reponse["destinations"][0]
    assert premiere["gare"]["id"] == VIF
    assert premiere["justification"].startswith("18 min de train direct depuis Grenoble.")
    # La difficulté n'existe pas dans les données : l'application le dit au lieu de faire semblant.
    assert any("difficulté" in a for a in reponse["avertissements"])


def test_conversation_garde_le_contexte(client):
    premiere = demander(client, QUESTION_SUJET)
    suite = demander(client, "Et si je préfère finalement quelque chose de culturel ?", contexte=premiere["criteres"])
    assert suite["origine"]["id"] == GRENOBLE
    assert suite["criteres_appliques"]["duree_max_min"] == 90
    assert suite["criteres_appliques"]["themes"] == ["culture"]
    assert [d["gare"]["id"] for d in suite["destinations"]] == [VOIRON, CHAMBERY]


def test_gare_selectionnee_sur_la_carte(client):
    autour = demander(client, "Que puis-je faire autour de cette gare ?", gare_selectionnee=ANNECY)
    assert autour["mode"] == "autour"
    assert autour["destinations"][0]["gare"]["id"] == ANNECY
    assert autour["destinations"][0]["trajet"] is None
    # Sans « autour », la gare sélectionnée sert de point de départ.
    depart = demander(client, "du patrimoine", gare_selectionnee=VOIRON)
    assert depart["mode"] == "destinations" and depart["origine"]["id"] == VOIRON
    assert any("estimations" in a for a in depart["avertissements"])  # Chambéry via Grenoble


def test_aucun_resultat_est_dit_clairement(client):
    reponse = demander(client, "Que faire avec deux enfants ?")
    assert reponse["destinations"] == []
    assert "aucune n'a de point d'intérêt « famille » à moins de 25 min à pied" in reponse["introduction"]
    assert "En acceptant 26 min de marche" in reponse["introduction"]
    assert any("Grenoble utilisée par défaut" in a for a in reponse["avertissements"])


def test_sans_theme_on_propose_des_activites(client):
    """« Une sortie » sans précision : ni hôtel ni festival dans les lieux proposés."""
    reponse = demander(client, "Une sortie à moins d'une heure de Grenoble")
    themes_proposes = {t for d in reponse["destinations"] for p in d["pois"] for t in p["themes"]}
    assert reponse["destinations"] and not themes_proposes & {"hebergement", "evenement"}
    lieux = {p["nom"] for d in reponse["destinations"] for p in d["pois"]}
    assert "Hôtel d'essai de la Gare" not in lieux


def test_evenement_demande_avertit_sur_les_dates(client):
    reponse = demander(client, "un festival à moins de 2 heures de Grenoble")
    assert any("dates des événements" in a for a in reponse["avertissements"])


def test_origine_inconnue(client):
    reponse = demander(client, "une randonnée depuis Clermont-Ferrand")
    assert reponse["destinations"] == [] and reponse["origine"] is None
    assert "« Clermont-Ferrand »" in reponse["introduction"]


# --- Avec un LLM simulé ---------------------------------------------------------------
def test_llm_qui_invente(client, monkeypatch):
    """Le LLM renvoie un thème inconnu et justifie une gare qui n'est pas dans les résultats."""

    def faux_llm(systeme, _utilisateur):
        if "extrais des critères" in systeme:
            return {"origine": "Grenoble", "duree_max_min": 90, "marche_max_min": 20, "themes": ["randonnee", "licornes"]}, {}
        return {"introduction": "Deux idées.", "justifications": {VIF: "Vif, pour son sentier.", "00000000": "Chamonix !"}}, {}

    monkeypatch.setattr(config, "LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setattr(config, "LLM_MODEL", "modele-test")
    monkeypatch.setattr(llm, "completer_json", faux_llm)
    reponse = demander(client, "une randonnée pas loin")
    assert reponse["moteur"] == {"extraction": "llm", "redaction": "llm"}
    assert reponse["criteres"]["themes"] == ["randonnee"]
    assert [d["gare"]["id"] for d in reponse["destinations"]] == [VIF, MONESTIER]  # Annecy trop loin, Clelles trop de marche
    assert reponse["destinations"][0]["justification"] == "Vif, pour son sentier."
    assert "Chamonix" not in str(reponse)
    # La gare non justifiée par le LLM garde sa justification par gabarit.
    assert reponse["destinations"][1]["justification"].startswith("42 min de train direct")


def test_llm_en_panne_bascule_sur_les_regles(client, monkeypatch):
    def llm_en_panne(_systeme, _utilisateur):
        raise llm.ErreurLLM("délai dépassé")

    monkeypatch.setattr(config, "LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setattr(config, "LLM_MODEL", "modele-test")
    monkeypatch.setattr(llm, "completer_json", llm_en_panne)
    reponse = demander(client, QUESTION_SUJET)
    assert reponse["moteur"] == {"extraction": "regles", "redaction": "gabarit"}
    assert reponse["destinations"][0]["gare"]["id"] == VIF
    assert any("indisponible" in a for a in reponse["avertissements"])
