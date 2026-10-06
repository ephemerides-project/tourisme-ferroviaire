"""Géométrie des voies ferrées — source : OpenStreetMap, via le service Overpass.

OpenRailwayMap n'est qu'un rendu d'OpenStreetMap : ses tuiles sont des images, on ne peut
rien calculer dessus. On télécharge donc les mêmes données sous forme de lignes (les « ways »
`railway=rail`), on en fait un graphe, puis on cherche le plus court chemin le long des voies
entre deux arrêts successifs d'un train.

Étape facultative : sans fichier de voies, les tracés restent des segments droits entre arrêts.
"""

from __future__ import annotations

import heapq
import json
import math
from pathlib import Path

import pandas as pd
import requests

SERVEURS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
TYPES_DE_VOIE = "rail|narrow_gauge|light_rail"  # narrow_gauge : la ligne Saint-Gervais - Vallorcine
SERVICES_EXCLUS = {"yard", "spur"}  # voies de triage et embranchements : aucun train de voyageurs
MARGE_DEG = 0.15  # marge autour des gares pour la zone téléchargée (environ 15 km)
RAYON_ACCROCHAGE_M = 400  # distance max entre un arrêt et la voie la plus proche
DETOUR_MAX = 2.5  # un chemin plus long que 2,5 fois la ligne droite (+ 2 km) est refusé
TOLERANCE_M = 15  # précision gardée quand on allège un tracé
TAILLE_CASE_DEG = 0.005  # grille de recherche du nœud le plus proche (cases d'environ 500 m)

Point = tuple[float, float]  # (lat, lon)


def _distance_m(a, b) -> float:
    """Distance en mètres entre deux points proches (approximation plane, suffisante à cette échelle)."""
    x = math.radians(b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    y = math.radians(b[0] - a[0])
    return 6371000 * math.hypot(x, y)


# --- Acquisition -------------------------------------------------------------
def requete(gares: pd.DataFrame) -> str:
    """Requête Overpass : toutes les voies ferrées du rectangle qui contient les gares."""
    sud, nord = gares["lat"].min() - MARGE_DEG, gares["lat"].max() + MARGE_DEG
    ouest, est = gares["lon"].min() - MARGE_DEG, gares["lon"].max() + MARGE_DEG
    return (
        "[out:json][timeout:300];"
        f'way["railway"~"^({TYPES_DE_VOIE})$"]({sud:.4f},{ouest:.4f},{nord:.4f},{est:.4f});'
        "out geom;"
    )


def telecharger(gares: pd.DataFrame, cible: Path, forcer: bool = False) -> Path:
    """Enregistre la réponse d'Overpass dans `cible`. Essaie chaque serveur à tour de rôle."""
    if cible.exists() and not forcer:
        print(f"  déjà présent : {cible.name} ({cible.stat().st_size / 1e6:.1f} Mo)")
        return cible
    erreur: Exception | None = None
    for serveur in SERVEURS:
        print(f"  téléchargement : voies ferrées OpenStreetMap ({serveur})")
        partiel = cible.with_suffix(cible.suffix + ".partiel")
        try:
            with requests.post(
                serveur,
                data={"data": requete(gares)},
                stream=True,
                timeout=(30, 600),
                headers={"User-Agent": "projet-etudiant-tourisme-ferroviaire"},
            ) as r:
                r.raise_for_status()
                with partiel.open("wb") as f:
                    for bloc in r.iter_content(chunk_size=1 << 20):
                        f.write(bloc)
        except requests.RequestException as e:
            erreur = e
            print(f"    échec : {e}")
            continue
        partiel.replace(cible)
        print(f"    -> {cible.name} ({cible.stat().st_size / 1e6:.1f} Mo)")
        return cible
    raise RuntimeError(f"Aucun serveur Overpass n'a répondu : {erreur}")


# --- Graphe des voies ----------------------------------------------------------
class Reseau:
    """Les voies sous forme de graphe : un nœud par point d'OpenStreetMap, une arête entre deux points voisins."""

    def __init__(self) -> None:
        self.positions: dict[int, Point] = {}
        self.voisins: dict[int, list[tuple[int, float]]] = {}  # nœud -> [(voisin, longueur en m)]
        self._cases: dict[tuple[int, int], list[int]] = {}
        self.remarque: str | None = None  # message d'Overpass quand sa réponse est incomplète

    def ajouter_voie(self, noeuds: list[int], points: list[Point]) -> None:
        for noeud, point in zip(noeuds, points):
            if noeud not in self.positions:
                self.positions[noeud] = point
                self.voisins[noeud] = []
                self._cases.setdefault(self._case(point), []).append(noeud)
        for a, b in zip(noeuds, noeuds[1:]):
            longueur = _distance_m(self.positions[a], self.positions[b])
            self.voisins[a].append((b, longueur))
            self.voisins[b].append((a, longueur))

    @staticmethod
    def _case(point) -> tuple[int, int]:
        return int(point[0] // TAILLE_CASE_DEG), int(point[1] // TAILLE_CASE_DEG)

    def noeud_proche(self, point) -> int | None:
        """Le nœud du réseau le plus proche du point, s'il y en a un à moins de 400 m."""
        ligne, colonne = self._case(point)
        meilleur, distance_min = None, RAYON_ACCROCHAGE_M
        for i in (ligne - 1, ligne, ligne + 1):
            for j in (colonne - 1, colonne, colonne + 1):
                for noeud in self._cases.get((i, j), ()):
                    distance = _distance_m(point, self.positions[noeud])
                    if distance < distance_min:
                        meilleur, distance_min = noeud, distance
        return meilleur

    def chemin(self, depart: int, arrivee: int, longueur_max: float) -> list[int] | None:
        """Plus court chemin entre deux nœuds (algorithme A*), ou None s'il dépasse `longueur_max`.

        A* est un Dijkstra qui explore d'abord les nœuds dont « distance parcourue + distance
        à vol d'oiseau jusqu'à l'arrivée » est la plus petite : il va droit vers le but.
        """
        cible = self.positions[arrivee]
        parcouru = {depart: 0.0}
        precedent: dict[int, int] = {}
        termines: set[int] = set()
        file = [(_distance_m(self.positions[depart], cible), depart)]
        while file:
            _, noeud = heapq.heappop(file)
            if noeud == arrivee:
                trajet = [noeud]
                while trajet[-1] != depart:
                    trajet.append(precedent[trajet[-1]])
                return trajet[::-1]
            if noeud in termines:
                continue
            termines.add(noeud)
            for voisin, longueur in self.voisins[noeud]:
                distance = parcouru[noeud] + longueur
                if distance >= parcouru.get(voisin, math.inf):
                    continue
                estimation = distance + _distance_m(self.positions[voisin], cible)
                if estimation > longueur_max:
                    continue
                parcouru[voisin] = distance
                precedent[voisin] = noeud
                heapq.heappush(file, (estimation, voisin))
        return None

    def troncon(self, a, b) -> list[list[float]] | None:
        """Tracé allégé le long des voies entre deux arrêts, ou None si aucun chemin raisonnable."""
        depart, arrivee = self.noeud_proche(a), self.noeud_proche(b)
        if depart is None or arrivee is None or depart == arrivee:
            return None
        noeuds = self.chemin(depart, arrivee, DETOUR_MAX * _distance_m(a, b) + 2000)
        if noeuds is None:
            return None
        return [[round(lat, 5), round(lon, 5)] for lat, lon in simplifier([self.positions[n] for n in noeuds])]


def lire(chemin: Path) -> Reseau:
    """Construit le graphe à partir de la réponse d'Overpass (format JSON, `out geom`)."""
    contenu = json.loads(chemin.read_text(encoding="utf-8"))
    reseau = Reseau()
    reseau.remarque = contenu.get("remark")
    for element in contenu.get("elements", []):
        if element.get("type") != "way" or element.get("tags", {}).get("service") in SERVICES_EXCLUS:
            continue
        noeuds, points = [], []
        for noeud, position in zip(element.get("nodes", []), element.get("geometry", [])):
            if position:  # un point peut manquer en bord de zone
                noeuds.append(noeud)
                points.append((position["lat"], position["lon"]))
        reseau.ajouter_voie(noeuds, points)
    return reseau


# --- Allègement d'un tracé -----------------------------------------------------
def _ecart_m(p, a, b) -> float:
    """Distance en mètres entre le point p et le segment [a, b]."""
    echelle = math.cos(math.radians(a[0]))
    px, py = (p[1] - a[1]) * echelle, p[0] - a[0]
    bx, by = (b[1] - a[1]) * echelle, b[0] - a[0]
    longueur2 = bx * bx + by * by
    t = 0.0 if longueur2 == 0 else max(0.0, min(1.0, (px * bx + py * by) / longueur2))
    return math.radians(math.hypot(px - t * bx, py - t * by)) * 6371000


def simplifier(points: list, tolerance_m: float = TOLERANCE_M) -> list:
    """Retire les points inutiles d'une ligne (algorithme de Douglas-Peucker).

    On garde les deux extrémités ; on cherche le point le plus éloigné du segment qui les relie ;
    s'il s'en écarte de plus de `tolerance_m`, on le garde et on recommence de chaque côté.
    Une voie rectiligne de 10 km passe ainsi de plusieurs centaines de points à deux.
    """
    if len(points) < 3:
        return list(points)
    garder = [False] * len(points)
    garder[0] = garder[-1] = True
    a_traiter = [(0, len(points) - 1)]
    while a_traiter:
        debut, fin = a_traiter.pop()
        plus_loin, ecart_max = None, tolerance_m
        for i in range(debut + 1, fin):
            ecart = _ecart_m(points[i], points[debut], points[fin])
            if ecart > ecart_max:
                plus_loin, ecart_max = i, ecart
        if plus_loin is not None:
            garder[plus_loin] = True
            a_traiter += [(debut, plus_loin), (plus_loin, fin)]
    return [point for point, retenu in zip(points, garder) if retenu]


# --- Application aux tracés des liaisons -----------------------------------------
def suivre(traces: list, reseau: Reseau) -> tuple[list, dict]:
    """Remplace, dans chaque tracé, les segments droits entre arrêts par le chemin le long des voies.

    Un tracé est la liste des arrêts d'un train : [[lat, lon], ...]. Le résultat commence et finit
    aux mêmes arrêts ; entre deux arrêts, il suit les voies quand un chemin existe, sinon il reste droit.
    """
    connus: dict[tuple, list | None] = {}  # un même tronçon sert à beaucoup de liaisons
    resultat = []
    for trace in traces:
        if not isinstance(trace, list) or len(trace) < 2:
            resultat.append(None)
            continue
        points = [trace[0]]
        for a, b in zip(trace, trace[1:]):
            cle = (tuple(a), tuple(b))
            if cle not in connus:
                retour = (cle[1], cle[0])
                if retour in connus:  # même tronçon dans l'autre sens : on le retourne
                    connus[cle] = connus[retour][::-1] if connus[retour] else None
                else:
                    connus[cle] = reseau.troncon(a, b)
            for point in connus[cle] or [b]:
                if point != points[-1]:  # pas de doublon quand l'arrêt est exactement sur la voie
                    points.append(point)
        if points[-1] != trace[-1]:
            points.append(trace[-1])
        resultat.append(points)
    bilan = {"troncons": len(connus), "sur_les_voies": sum(1 for t in connus.values() if t)}
    return resultat, bilan
