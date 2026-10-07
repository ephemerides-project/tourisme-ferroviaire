"""Tracés le long des voies ferrées : graphe, plus court chemin, allègement. Sans base ni réseau."""

from __future__ import annotations

import json
import math

import pandas as pd

from ingestion import pipeline, voies

A, B = [45.0, 5.0], [45.0, 5.2]  # deux arrêts distants d'environ 15,7 km
LOIN = [46.0, 6.0]  # un arrêt sans aucune voie à proximité


def _voie(identifiant: int, points: list[tuple[int, float, float]], **tags) -> dict:
    """Une voie au format renvoyé par Overpass (`out geom`) : points = [(id du nœud, lat, lon)]."""
    return {
        "type": "way",
        "id": identifiant,
        "nodes": [p[0] for p in points],
        "geometry": [{"lat": p[1], "lon": p[2]} for p in points],
        "tags": {"railway": "rail", **tags},
    }


def _fichier_de_voies(tmp_path):
    """Un petit réseau inventé : une voie courbe de A à B, un embranchement, et un raccourci de triage."""
    courbe = [(100 + i, 45.0 + 0.02 * math.sin(math.pi * i / 40), 5.0 + 0.2 * i / 40) for i in range(41)]
    embranchement = [(120, courbe[20][1], courbe[20][2]), (200, 45.06, 5.1), (201, 45.1, 5.1)]
    raccourci = [(100, 45.0, 5.0), (140, 45.0, 5.2)]  # ligne droite de A à B, mais voie de triage
    chemin = tmp_path / "voies-osm.json"
    chemin.write_text(
        json.dumps({"elements": [_voie(1, courbe), _voie(2, embranchement), _voie(3, raccourci, service="yard")]}),
        encoding="utf-8",
    )
    return chemin


def test_le_troncon_suit_la_voie_et_ignore_le_triage(tmp_path):
    reseau = voies.lire(_fichier_de_voies(tmp_path))
    troncon = reseau.troncon(A, B)
    assert troncon[0] == A and troncon[-1] == B
    sommet = max(troncon, key=lambda p: p[0])
    assert abs(sommet[0] - 45.02) < 0.001 and abs(sommet[1] - 5.1) < 0.02  # passe par le haut de la courbe
    assert 3 < len(troncon) < 41  # allégé, mais pas réduit à une ligne droite


def test_pas_de_troncon_loin_des_voies_ni_au_prix_d_un_grand_detour(tmp_path):
    reseau = voies.lire(_fichier_de_voies(tmp_path))
    assert reseau.troncon(A, LOIN) is None
    # Deux points à 300 m l'un de l'autre, reliés seulement par un demi-tour de 20 km : refusé.
    en_u = [(1, 45.0, 5.0), (2, 45.09, 5.0), (3, 45.09, 5.004), (4, 45.0, 5.004)]
    detour = voies.Reseau()
    detour.ajouter_voie([p[0] for p in en_u], [(p[1], p[2]) for p in en_u])
    assert detour.troncon([45.0, 5.0], [45.0, 5.004]) is None


def test_simplifier_garde_les_virages_pas_les_points_alignes():
    droite = [(45.0, 5.0 + i / 1000) for i in range(50)]
    assert voies.simplifier(droite) == [droite[0], droite[-1]]
    coude = droite + [(45.0 + i / 1000, 5.049) for i in range(1, 50)]
    assert voies.simplifier(coude) == [coude[0], droite[-1], coude[-1]]


def test_suivre_remplace_les_segments_droits(tmp_path):
    reseau = voies.lire(_fichier_de_voies(tmp_path))
    traces, bilan = voies.suivre([[A, B, LOIN], [B, A], None], reseau)
    aller, retour, absent = traces
    assert aller[0] == A and aller[-1] == LOIN and len(aller) > 5  # A -> B par la voie, puis tout droit
    assert retour == aller[:-1][::-1]  # le même tronçon, parcouru dans l'autre sens
    assert absent is None
    assert bilan == {"troncons": 3, "sur_les_voies": 2}


def test_zones_couvrent_les_gares_avec_une_marge():
    gares = pd.DataFrame({"lat": [45.0, 46.2], "lon": [5.0, 6.0]})
    decoupage = voies.zones(gares)
    assert decoupage == [(44.85, 4.85, 45.85, 5.85), (44.85, 5.85, 45.85, 6.15), (45.85, 4.85, 46.35, 5.85), (45.85, 5.85, 46.35, 6.15)]
    assert "(44.85,4.85,45.85,5.85)" in voies.requete(decoupage[0])


class _Reponse:
    def __init__(self, statut: int, contenu: dict):
        self.status_code, self._contenu = statut, contenu

    def raise_for_status(self):
        if self.status_code >= 400:
            raise voies.requests.HTTPError(f"{self.status_code} Server Error")

    def json(self):
        return self._contenu


def test_telechargement_par_zones_avec_reprise(tmp_path, monkeypatch):
    """Un 504 puis une réponse abandonnée en route : on réessaie. Une voie vue dans deux zones : gardée une fois."""
    gares = pd.DataFrame({"lat": [45.0, 45.1], "lon": [5.0, 6.0]})  # deux zones côte à côte
    voie = _voie(7, [(1, 45.0, 5.8), (2, 45.0, 5.9)])
    reponses = [
        _Reponse(504, {}),
        _Reponse(200, {"elements": [], "remark": "runtime error: Query timed out"}),
        _Reponse(200, {"elements": [voie]}),
        _Reponse(200, {"elements": [voie, _voie(8, [(2, 45.0, 5.9), (3, 45.0, 6.0)])]}),
    ]
    appels = []
    monkeypatch.setattr(voies.requests, "post", lambda url, **_: (appels.append(url), reponses.pop(0))[1])
    monkeypatch.setattr(voies.time, "sleep", lambda _secondes: None)

    cible = voies.telecharger(gares, tmp_path / "voies-osm.json")
    assert len(appels) == 4 and appels[0] != appels[1]  # le deuxième essai change de serveur
    assert sorted(e["id"] for e in json.loads(cible.read_text())["elements"]) == [7, 8]
    assert len(voies.lire(cible).positions) == 3

    voies.telecharger(gares, cible)  # déjà présent : aucun nouvel appel
    assert len(appels) == 4


def test_zone_en_echec_puis_reprise(tmp_path, monkeypatch):
    gares = pd.DataFrame({"lat": [45.0, 45.1], "lon": [5.0, 6.0]})
    monkeypatch.setattr(voies.time, "sleep", lambda _secondes: None)
    etat = {"en_panne": False, "appels": 0}

    def post(url, **_):
        etat["appels"] += 1
        return _Reponse(504 if etat["en_panne"] else 200, {"elements": []})

    monkeypatch.setattr(voies.requests, "post", post)
    # première zone obtenue, puis panne générale sur la seconde
    original = voies._telecharger_zone

    def zone_puis_panne(zone):
        resultat = original(zone)
        etat["en_panne"] = True
        return resultat

    monkeypatch.setattr(voies, "_telecharger_zone", zone_puis_panne)
    try:
        voies.telecharger(gares, tmp_path / "voies-osm.json")
        raise AssertionError("la seconde zone aurait dû échouer")
    except RuntimeError as erreur:
        assert "aucun serveur" in str(erreur)
    assert not (tmp_path / "voies-osm.json").exists()

    etat["en_panne"], etat["appels"] = False, 0
    voies.telecharger(gares, tmp_path / "voies-osm.json")
    assert etat["appels"] == 1  # seule la zone manquante est redemandée


def test_pipeline_sans_puis_avec_fichier_de_voies(tmp_path):
    messages: list[str] = []
    traces, bilan = pipeline._suivre_les_voies(tmp_path, None, [[A, B]], False, messages.append)
    assert traces == [[A, B]] and bilan == {} and "segments droits" in messages[0]

    _fichier_de_voies(tmp_path)
    traces, bilan = pipeline._suivre_les_voies(tmp_path, None, [[A, B]], False, messages.append)
    assert len(traces[0]) > 3 and bilan["sur_les_voies"] == 1 and bilan["noeuds_du_reseau"] == 43


def test_fichier_de_voies_illisible_ou_incomplet(tmp_path):
    messages: list[str] = []
    (tmp_path / "voies-osm.json").write_text("<html>erreur</html>", encoding="utf-8")
    traces, bilan = pipeline._suivre_les_voies(tmp_path, None, [[A, B]], False, messages.append)
    assert traces == [[A, B]] and bilan == {} and "illisible" in messages[-1]

    (tmp_path / "voies-osm.json").write_text('{"elements": [], "remark": "runtime error: timed out"}', encoding="utf-8")
    traces, bilan = pipeline._suivre_les_voies(tmp_path, None, [[A, B]], False, messages.append)
    assert traces == [[A, B]] and bilan["sur_les_voies"] == 0 and any("timed out" in m for m in messages)


# --- Lignes SNCF (GeoJSON) --------------------------------------------------------
C = [45.1, 5.1]  # un arrêt au bout d'une ligne qui se branche sur la ligne A - B


def _lignes_sncf(tmp_path):
    """Trois lignes inventées, au format du fichier SNCF : A - B, une branche vers C, un raccourci déclassé."""
    ligne_ab = {"type": "LineString", "coordinates": [[5.0 + i / 100, 45.0] for i in range(21)]}
    # La branche commence à 55 m de la ligne A - B, sans partager de point avec elle, et arrive en deux morceaux.
    branche = {"type": "MultiLineString", "coordinates": [[[5.1, 45.0005], [5.1, 45.05]], [[5.1, 45.05], [5.1, 45.1]]]}
    raccourci = {"type": "LineString", "coordinates": [[5.0, 45.0], [5.1, 45.1]]}
    formes = [
        {"type": "Feature", "geometry": ligne_ab, "properties": {"code_ligne": "1", "mnemo": "EXPLOITE"}},
        {"type": "Feature", "geometry": branche, "properties": {"code_ligne": "2", "mnemo": "EXPLOITE"}},
        {"type": "Feature", "geometry": raccourci, "properties": {"code_ligne": "3", "mnemo": "DECLASSE NON VENDU"}},
        {"type": "Feature", "geometry": None, "properties": {"code_ligne": "4"}},
    ]
    chemin = tmp_path / "lignes-sncf.geojson"
    chemin.write_text(json.dumps({"type": "FeatureCollection", "features": formes}), encoding="utf-8")
    return chemin


def test_lignes_sncf_bifurcation_raccordee_et_ligne_fermee_ignoree(tmp_path):
    reseau = voies.lire_lignes_sncf(_lignes_sncf(tmp_path))
    troncon = reseau.troncon(A, C)
    assert troncon[0] == A and troncon[-1] == C
    assert any(abs(lat - 45.0) < 0.001 and abs(lon - 5.1) < 0.001 for lat, lon in troncon)  # passe par la bifurcation
    assert len(troncon) >= 3  # donc pas par le raccourci déclassé, qui irait tout droit


def test_lignes_sncf_limitees_a_la_zone_des_gares(tmp_path):
    ici = pd.DataFrame({"lat": [45.0], "lon": [5.1]})
    ailleurs = pd.DataFrame({"lat": [48.0], "lon": [2.0]})
    assert len(voies.lire_lignes_sncf(_lignes_sncf(tmp_path), ici).positions) > 20
    assert len(voies.lire_lignes_sncf(_lignes_sncf(tmp_path), ailleurs).positions) == 0


def test_pipeline_prefere_les_lignes_sncf(tmp_path):
    messages: list[str] = []
    _lignes_sncf(tmp_path)
    (tmp_path / "voies-osm.json").write_text('{"elements": []}', encoding="utf-8")
    traces, bilan = pipeline._suivre_les_voies(tmp_path, None, [[A, C]], False, messages.append)
    assert bilan["sur_les_voies"] == 1 and "lignes-sncf.geojson" in messages[-1]
