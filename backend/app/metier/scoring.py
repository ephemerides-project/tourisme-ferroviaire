"""Classement des destinations : une formule explicite, sans LLM.

score = 35 % couverture des thèmes demandés
      + 20 % richesse de l'offre (nombre de POI correspondants)
      + 20 % temps de trajet (plus c'est court, mieux c'est)
      + 15 % marche depuis la gare (POI correspondant le plus proche)
      + 10 % fréquence des trains
      - 10 points par correspondance

Chaque composante vaut entre 0 et 1 ; le total est ramené sur 100.
Les poids sont des choix d'équipe : ils se discutent et se règlent ici.
"""

from __future__ import annotations

POIDS = {"themes": 0.35, "offre": 0.20, "trajet": 0.20, "marche": 0.15, "frequence": 0.10}
PENALITE_CORRESPONDANCE = 0.10
OFFRE_SATUREE_A = 5  # au-delà de 5 POI correspondants, la richesse ne rapporte plus
FREQUENCE_SATUREE_A = 10.0  # au-delà de 10 trains par jour, la fréquence ne rapporte plus


def _borner(x: float) -> float:
    return max(0.0, min(1.0, x))


def calculer(
    duree_min: int,
    duree_max: int,
    correspondances: int,
    trajets_jour: float,
    pois: list[dict],
    themes_demandes: list[str],
    marche_max: int,
) -> dict:
    """Renvoie le score sur 100 et le détail de chaque composante (pour l'expliquer à l'utilisateur).

    `pois` : points d'intérêt de la destination qui respectent déjà les filtres
    (thème et marche maximale). Chacun a au moins `themes` et `marche_min`.
    """
    if themes_demandes:
        couverts = {t for p in pois for t in p["themes"] if t in themes_demandes}
        themes = len(couverts) / len(themes_demandes)
    else:
        themes = 1.0 if pois else 0.0

    composantes = {
        "themes": themes,
        "offre": _borner(len(pois) / OFFRE_SATUREE_A),
        "trajet": _borner(1 - duree_min / duree_max) if duree_max else 0.0,
        "marche": _borner(1 - min(p["marche_min"] for p in pois) / marche_max) if pois and marche_max else 0.0,
        "frequence": _borner(trajets_jour / FREQUENCE_SATUREE_A),
    }
    penalite = PENALITE_CORRESPONDANCE * correspondances
    total = sum(POIDS[c] * v for c, v in composantes.items()) - penalite
    return {
        "total": round(100 * _borner(total)),
        "composantes": {c: round(v, 2) for c, v in composantes.items()},
        "penalite_correspondance": round(100 * penalite),
    }
