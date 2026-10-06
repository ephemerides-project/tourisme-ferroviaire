"""Nettoyage et normalisation des trois sources, sur le jeu d'essai (sans base de données)."""

import pandas as pd
import pytest

from app.themes import classer, enrichir_par_texte
from ingestion import gares_sncf, gtfs, poi_datatourisme
from tests.conftest import DOSSIER_EXEMPLE

GRENOBLE, GIERES, VIF, CLELLES = "87747006", "87747402", "87747139", "87747170"


@pytest.fixture(scope="module")
def gares():
    table, _bilan = gares_sncf.normaliser_gares(gares_sncf.lire_gares(DOSSIER_EXEMPLE / "gares-de-voyageurs.json"))
    return table


@pytest.fixture(scope="module")
def tables_gtfs():
    return gtfs.lire_gtfs(DOSSIER_EXEMPLE / "gtfs")


def liaison(liaisons: pd.DataFrame, origine: str, destination: str) -> pd.Series:
    return liaisons[(liaisons["origine_id"] == origine) & (liaisons["destination_id"] == destination)].iloc[0]


# --- Gares SNCF ---------------------------------------------------------------
def test_gares_nettoyage():
    brut = gares_sncf.lire_gares(DOSSIER_EXEMPLE / "gares-de-voyageurs.json")
    table, bilan = gares_sncf.normaliser_gares(brut)
    assert bilan == {"lues": 16, "sans_position": 1, "sans_uic": 0, "hors_region": 1, "doublons": 1, "retenues": 13}
    assert "Paris Gare de Lyon" not in set(table["nom"])  # hors région
    grenoble = table[table["id"] == GRENOBLE].iloc[0]
    assert grenoble["codes_uic"] == ["87747006", "87747014"]
    assert (grenoble["departement"], grenoble["lat"], grenoble["lon"]) == ("38", 45.1915, 5.7145)


def test_gares_export_csv_avec_libelles():
    """L'export CSV de la SNCF utilise des libellés (« Nom_Gare », « Code(s) UIC ») et « lat, lon »."""
    ligne = {"Nom_Gare": "Voiron", "Trigramme": "VOI", "Segment(s) DRG": "B", "Position géographique": "45.3643, 5.5935",
             "Code Commune": "38563", "Code(s) UIC": "0087747337"}
    table, _ = gares_sncf.normaliser_gares([ligne])
    voiron = table.iloc[0]
    assert (voiron["id"], voiron["nom"], voiron["trigramme"], voiron["lat"], voiron["lon"]) == ("87747337", "Voiron", "VOI", 45.3643, 5.5935)


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [("87747006", ["87747006"]), ("87747006;87747014", ["87747006", "87747014"]), (87747006, ["87747006"]),
     (["0087747006"], ["87747006"]), (None, []), ("inconnu", [])],
)
def test_codes_uic(valeur, attendu):
    assert gares_sncf.codes_uic(valeur) == attendu


# --- GTFS -----------------------------------------------------------------------
def test_heure_apres_minuit():
    assert list(gtfs.heure_en_minutes(pd.Series(["08:15:00", "25:10:00", "", "abc"])).fillna(-1)) == [495, 1510, -1, -1]


def test_uic_depuis_stop_id():
    assert gtfs.uic_depuis_stop_id("StopPoint:OCETrain TER-87747006") == "87747006"
    assert gtfs.uic_depuis_stop_id("StopArea:OCE87747006") == "87747006"
    assert gtfs.uic_depuis_stop_id("arret-sans-code") is None


def test_rattachement_par_uic_puis_par_proximite(gares, tables_gtfs):
    correspondance, bilan = gtfs.rattacher_arrets(tables_gtfs["stops"], gares)
    assert correspondance["StopPoint:OCETrain TER-87747006"] == GRENOBLE
    assert correspondance["StopPoint:OCETrain TER-87999999"] == GIERES  # code inconnu, à 80 m de la gare
    assert not any("87686006" in arret for arret in correspondance)  # Paris : hors région, non rattaché
    assert bilan["par_proximite"] == 1


def test_liaisons(gares, tables_gtfs):
    correspondance, _ = gtfs.rattacher_arrets(tables_gtfs["stops"], gares)
    liaisons = gtfs.calculer_liaisons(tables_gtfs, correspondance, types_route=(2,))
    # Trois trains Grenoble -> Vif : 18, 18 et 22 min. La médiane vaut 18.
    assert liaison(liaisons, GRENOBLE, VIF)["duree_min"] == 18
    # 2 trains x 5 jours + 1 train x 2 jours, sur 7 jours couverts = 12 / 7.
    assert liaison(liaisons, GRENOBLE, VIF)["trajets_jour"] == pytest.approx(1.71)
    # Le dernier Clelles -> Grenoble part à 23h30 et arrive à 24h30 : 60 min, pas -1380.
    assert liaison(liaisons, CLELLES, GRENOBLE)["duree_min"] == 60
    assert liaison(liaisons, GRENOBLE, GIERES)["duree_min"] == 9
    assert (liaisons["duree_min"] > 0).all()
    assert (liaisons["origine_id"] != liaisons["destination_id"]).all()


def test_trace_par_les_arrets_intermediaires(gares, tables_gtfs):
    """Le tracé Grenoble -> Clelles passe par Vif et Monestier, dans l'ordre du train."""
    correspondance, _ = gtfs.rattacher_arrets(tables_gtfs["stops"], gares)
    liaisons = gtfs.calculer_liaisons(tables_gtfs, correspondance, types_route=(2,))
    trace = liaison(liaisons, GRENOBLE, CLELLES)["trace"]
    assert trace == [[45.1915, 5.7145], [45.056, 5.67], [44.917, 5.635], [44.826, 5.624]]
    # Sens inverse : mêmes points, ordre inversé.
    assert liaison(liaisons, CLELLES, GRENOBLE)["trace"] == trace[::-1]
    # Chaque liaison a un tracé d'au moins deux points.
    assert all(len(t) >= 2 for t in liaisons["trace"])


def test_liaisons_avec_les_cars(gares, tables_gtfs):
    """En incluant les cars (type 3), le car Grenoble -> Vif en 40 min entre dans la médiane."""
    correspondance, _ = gtfs.rattacher_arrets(tables_gtfs["stops"], gares)
    liaisons = gtfs.calculer_liaisons(tables_gtfs, correspondance, types_route=(2, 3))
    assert liaison(liaisons, GRENOBLE, VIF)["duree_min"] == 20  # médiane de 18, 18, 22, 40


# --- Points d'intérêt ---------------------------------------------------------------
def test_poi_nettoyage():
    poi, bilan = poi_datatourisme.normaliser_poi(poi_datatourisme.lire_csv(DOSSIER_EXEMPLE / "datatourisme-exemple.csv"))
    assert (bilan["lus"], bilan["sans_nom_ou_position"], bilan["hors_region"], bilan["doublons"], bilan["retenus"]) == (31, 1, 1, 1, 28)
    assert bilan["types_non_classes"] == [("SpaAndWellness", 1)]
    assert poi["id"].is_unique
    sentier = poi[poi["nom"] == "Sentier d'essai des Coteaux"].iloc[0]
    assert sentier["themes"] == ["randonnee"]
    assert (sentier["commune"], sentier["code_postal"], sentier["source"]) == ("Vif", "38450", "DATAtourisme")
    assert sentier["types_source"] == ["PlaceOfInterest", "PointOfInterest", "Tour", "WalkingTour"]


def test_poi_autre_separateur_et_colonnes_manquantes(tmp_path):
    fichier = tmp_path / "poi.csv"
    fichier.write_text("Nom_du_POI;Categories_de_POI;Latitude;Longitude\nMusée;schema:Museum;45,19;5,72\n", encoding="utf-8")
    poi, _ = poi_datatourisme.normaliser_poi(poi_datatourisme.lire_csv(fichier))
    assert (poi.iloc[0]["lat"], poi.iloc[0]["lon"], poi.iloc[0]["themes"]) == (45.19, 5.72, ["culture"])
    assert poi.iloc[0]["id"].startswith("local:")  # pas d'URI : identifiant calculé

    fichier.write_text("titre,x,y\nMusée,1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Colonnes introuvables"):
        poi_datatourisme.normaliser_poi(poi_datatourisme.lire_csv(fichier))


# --- Thèmes -------------------------------------------------------------------------
def test_classement_des_types():
    onto = "https://www.datatourisme.fr/ontology/core#"
    assert classer([onto + "PlaceOfInterest", onto + "Castle"]) == ["patrimoine"]
    assert classer([onto + "WalkingTour"]) == ["randonnee"]
    assert classer([onto + "Transport"]) == []  # « Transport » contient « sport » : faux ami écarté
    assert classer([onto + "PointOfInterest"]) == []
    # Types rencontrés au premier chargement réel
    assert classer(["schema:LodgingBusiness"]) == ["hebergement"]
    assert classer(["schema:Landform"]) == ["nature"]
    assert classer(["schema:Park"]) == ["nature"]
    assert classer(["schema:ParkingFacility"]) == []  # « Park » n'est reconnu que par son nom exact
    assert classer(["schema:Store"]) == []


def test_enrichissement_par_le_texte():
    assert enrichir_par_texte(["nature"], "Lac des Alpages", "Balade en montagne adaptée aux enfants") == ["famille", "montagne", "nature"]
    assert enrichir_par_texte([], "Sentier botanique", None) == ["randonnee"]
    assert enrichir_par_texte(["hebergement"], "Hôtel de la Montagne", "Idéal en famille") == ["hebergement"]
    # « Practice » (activité encadrée) : loisir par défaut, et gastronomie quand le nom parle de vin
    activite = classer(["schema:Product", "schema:Practice"])
    assert activite == ["sport_loisirs"]
    assert enrichir_par_texte(activite, "Week end dégustation : les fondamentaux", None) == ["gastronomie", "sport_loisirs"]
    assert enrichir_par_texte(activite, "Canoë Kayak", None) == ["sport_loisirs"]
