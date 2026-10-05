"""Formule de classement."""

from app.metier.scoring import calculer

POI_RANDO = {"themes": ["randonnee"], "marche_min": 5}
POI_NATURE = {"themes": ["nature"], "marche_min": 10}


def test_detail_du_calcul():
    """Un cas calculé à la main, pour vérifier chaque composante."""
    score = calculer(
        duree_min=30, duree_max=120, correspondances=0, trajets_jour=5,
        pois=[POI_RANDO, POI_NATURE], themes_demandes=["randonnee", "nature"], marche_max=20,
    )
    assert score["composantes"] == {"themes": 1.0, "offre": 0.4, "trajet": 0.75, "marche": 0.75, "frequence": 0.5}
    # 0,35x1 + 0,20x0,4 + 0,20x0,75 + 0,15x0,75 + 0,10x0,5 = 0,7425
    assert score["total"] == 74
    assert score["penalite_correspondance"] == 0


def test_couverture_partielle_des_themes():
    complet = calculer(30, 120, 0, 5, [POI_RANDO, POI_NATURE], ["randonnee", "nature"], 20)
    partiel = calculer(30, 120, 0, 5, [POI_RANDO, POI_RANDO], ["randonnee", "nature"], 20)
    assert partiel["composantes"]["themes"] == 0.5
    assert partiel["total"] < complet["total"]


def test_correspondance_penalisee():
    direct = calculer(60, 120, 0, 5, [POI_RANDO], ["randonnee"], 20)
    avec_correspondance = calculer(60, 120, 1, 5, [POI_RANDO], ["randonnee"], 20)
    assert direct["total"] - avec_correspondance["total"] == 10


def test_plus_court_est_mieux():
    proche = calculer(20, 120, 0, 5, [POI_RANDO], ["randonnee"], 20)
    loin = calculer(110, 120, 0, 5, [POI_RANDO], ["randonnee"], 20)
    assert proche["total"] > loin["total"]


def test_score_borne():
    score = calculer(119, 120, 3, 0, [{"themes": ["culture"], "marche_min": 20}], ["randonnee"], 20)
    assert score["total"] == 0
