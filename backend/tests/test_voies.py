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


def test_requete_couvre_les_gares_avec_une_marge():
    gares = pd.DataFrame({"lat": [45.0, 46.0], "lon": [5.0, 6.0]})
    assert "(44.8500,4.8500,46.1500,6.1500)" in voies.requete(gares)


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
