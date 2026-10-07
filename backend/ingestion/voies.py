"""Géométrie des voies ferrées, pour que les tracés des trajets suivent les rails.

Deux sources possibles, lues dans le même graphe :
- SNCF Open Data, « formes des lignes du Réseau Ferré National » : le tracé officiel de chaque
  ligne, en un seul fichier GeoJSON. C'est la source par défaut.
- OpenStreetMap, via le service Overpass : les mêmes données qu'OpenRailwayMap. Gardée en secours,
  car les serveurs publics d'Overpass répondent mal.

Dans les deux cas on construit un graphe, puis on cherche le plus court chemin le long des voies
entre deux arrêts successifs d'un train.

Étape facultative : sans fichier de voies, les tracés restent des segments droits entre arrêts.

Usage : `python -m ingestion.voies` télécharge les lignes SNCF (`--osm` pour OpenStreetMap),
puis `python -m ingestion.pipeline` les utilise.
"""

from __future__ import annotations

import heapq
import json
import math
import time
from pathlib import Path

import pandas as pd
import requests

from app.texte import normaliser

URL_LIGNES_SNCF = (
    "https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets/formes-des-lignes-du-rfn/exports/geojson"
)
STATUTS_FERMES = ("declass", "ferme", "retranch", "neutralis", "depos")  # lignes où plus aucun train ne passe
RAYON_JONCTION_M = 150  # un bout de ligne est raccordé à la ligne voisine située à moins de 150 m

SERVEURS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
TAILLE_ZONE_DEG = 1.0  # la région est téléchargée par carrés d'un degré (environ 110 km sur 80)
ESSAIS = 3  # nombre de tours de serveurs avant d'abandonner une zone
ATTENTE_S = 20  # pause entre deux tours, allongée à chaque tour
PAUSE_S = 2  # pause entre deux zones
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
def zones(gares: pd.DataFrame) -> list[tuple[float, float, float, float]]:
    """Découpe le rectangle qui contient les gares en carrés d'un degré : (sud, ouest, nord, est).

    Demander toute la région d'un coup dépasse le temps accordé par les serveurs publics (erreur 504).
    """
    sud, nord = float(gares["lat"].min()) - MARGE_DEG, float(gares["lat"].max()) + MARGE_DEG
    ouest, est = float(gares["lon"].min()) - MARGE_DEG, float(gares["lon"].max()) + MARGE_DEG
    decoupage = []
    lat = sud
    while lat < nord:
        lon = ouest
        while lon < est:
            decoupage.append((round(lat, 4), round(lon, 4), round(min(lat + TAILLE_ZONE_DEG, nord), 4), round(min(lon + TAILLE_ZONE_DEG, est), 4)))
            lon += TAILLE_ZONE_DEG
        lat += TAILLE_ZONE_DEG
    return decoupage


def requete(zone: tuple[float, float, float, float]) -> str:
    """Requête Overpass : toutes les voies ferrées d'une zone, avec la position de chaque point."""
    sud, ouest, nord, est = zone
    return f'[out:json][timeout:120];way["railway"~"^({TYPES_DE_VOIE})$"]({sud},{ouest},{nord},{est});out geom;'


def _telecharger_zone(zone: tuple[float, float, float, float]) -> list[dict]:
    """Les voies d'une zone. Essaie chaque serveur, puis recommence après une pause (serveurs souvent chargés)."""
    erreur: Exception | None = None
    for essai in range(ESSAIS):
        for serveur in SERVEURS:
            try:
                r = requests.post(
                    serveur,
                    data={"data": requete(zone)},
                    timeout=(30, 300),
                    headers={"User-Agent": "projet-etudiant-tourisme-ferroviaire"},
                )
                r.raise_for_status()
                contenu = r.json()
                if contenu.get("remark"):  # Overpass répond 200 même quand il abandonne en cours de route
                    raise ValueError(contenu["remark"])
                return contenu.get("elements", [])
            except (requests.RequestException, ValueError) as e:
                erreur = e
                print(f"      échec sur {serveur.split('/')[2]} : {str(e)[:120]}")
        if essai < ESSAIS - 1:
            time.sleep(ATTENTE_S * (essai + 1))
    raise RuntimeError(f"zone {zone} : aucun serveur Overpass n'a répondu ({erreur})")


def telecharger(gares: pd.DataFrame, cible: Path, forcer: bool = False) -> Path:
    """Télécharge les voies zone par zone, puis les réunit dans `cible`.

    Chaque zone réussie est gardée dans un dossier voisin : si une zone échoue,
    relancer la commande reprend là où elle s'était arrêtée.
    """
    if cible.exists() and not forcer:
        print(f"  déjà présent : {cible.name} ({cible.stat().st_size / 1e6:.1f} Mo)")
        return cible
    dossier = cible.with_suffix(".zones")
    dossier.mkdir(parents=True, exist_ok=True)
    decoupage = zones(gares)
    for numero, zone in enumerate(decoupage, start=1):
        fichier = dossier / f"{zone[0]}_{zone[1]}.json"
        if fichier.exists():
            continue
        print(f"  voies ferrées OpenStreetMap : zone {numero}/{len(decoupage)}")
        fichier.write_text(json.dumps(_telecharger_zone(zone)), encoding="utf-8")
        time.sleep(PAUSE_S)  # on ménage un service public et gratuit

    # Une voie à cheval sur deux zones arrive deux fois : on ne la garde qu'une fois, grâce à son identifiant.
    voies_uniques: dict[int, dict] = {}
    for zone in decoupage:
        for element in json.loads((dossier / f"{zone[0]}_{zone[1]}.json").read_text(encoding="utf-8")):
            voies_uniques[element["id"]] = element
    cible.write_text(json.dumps({"elements": list(voies_uniques.values())}), encoding="utf-8")
    print(f"    -> {cible.name} ({cible.stat().st_size / 1e6:.1f} Mo, {len(voies_uniques)} voies)")
    return cible


# --- Graphe des voies ----------------------------------------------------------
class Reseau:
    """Les voies sous forme de graphe : un nœud par point d'OpenStreetMap, une arête entre deux points voisins."""

    def __init__(self) -> None:
        self.positions: dict[int, Point] = {}
        self.voisins: dict[int, list[tuple[int, float]]] = {}  # nœud -> [(voisin, longueur en m)]
        self._cases: dict[tuple[int, int], list[int]] = {}
        self._ligne: dict = {}  # nœud -> ligne qui l'a créé (sert à raccorder les lignes entre elles)
        self._extremites: list[tuple] = []  # (nœud, ligne) pour chaque bout de ligne
        self.remarque: str | None = None  # message d'Overpass quand sa réponse est incomplète

    def ajouter_voie(self, noeuds: list, points: list[Point], ligne=None) -> None:
        for noeud, point in zip(noeuds, points):
            if noeud not in self.positions:
                self.positions[noeud] = point
                self.voisins[noeud] = []
                self._ligne[noeud] = ligne
                self._cases.setdefault(self._case(point), []).append(noeud)
        for a, b in zip(noeuds, noeuds[1:]):
            if a != b:
                self._relier(a, b)
        if ligne is not None and noeuds:
            self._extremites += [(noeuds[0], ligne), (noeuds[-1], ligne)]

    def _relier(self, a, b) -> None:
        longueur = _distance_m(self.positions[a], self.positions[b])
        self.voisins[a].append((b, longueur))
        self.voisins[b].append((a, longueur))

    def relier_les_extremites(self, rayon_m: float = RAYON_JONCTION_M) -> int:
        """Raccorde chaque bout de ligne au point le plus proche d'une AUTRE ligne, à moins de `rayon_m`.

        Dans le fichier SNCF, une ligne qui se branche sur une autre s'arrête près d'elle sans
        partager de point avec elle : sans ce raccord, le graphe serait coupé à chaque bifurcation.
        """
        raccords = 0
        for noeud, ligne in self._extremites:
            point = self.positions[noeud]
            meilleur, distance_min = None, rayon_m
            for candidat in self._noeuds_autour(point):
                if candidat == noeud or self._ligne[candidat] == ligne:
                    continue
                distance = _distance_m(point, self.positions[candidat])
                if distance < distance_min:
                    meilleur, distance_min = candidat, distance
            if meilleur is not None:
                self._relier(noeud, meilleur)
                raccords += 1
        return raccords

    @staticmethod
    def _case(point) -> tuple[int, int]:
        return int(point[0] // TAILLE_CASE_DEG), int(point[1] // TAILLE_CASE_DEG)

    def _noeuds_autour(self, point):
        """Les nœuds de la case du point et des huit cases voisines."""
        ligne, colonne = self._case(point)
        for i in (ligne - 1, ligne, ligne + 1):
            for j in (colonne - 1, colonne, colonne + 1):
                yield from self._cases.get((i, j), ())

    def noeud_proche(self, point):
        """Le nœud du réseau le plus proche du point, s'il y en a un à moins de 400 m."""
        meilleur, distance_min = None, RAYON_ACCROCHAGE_M
        for noeud in self._noeuds_autour(point):
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


# --- Lignes SNCF (source par défaut) --------------------------------------------
def telecharger_lignes_sncf(cible: Path, forcer: bool = False) -> Path:
    """Télécharge le tracé officiel des lignes du réseau ferré national (un seul fichier GeoJSON)."""
    if cible.exists() and not forcer:
        print(f"  déjà présent : {cible.name} ({cible.stat().st_size / 1e6:.1f} Mo)")
        return cible
    print("  téléchargement : SNCF Open Data — formes des lignes du Réseau Ferré National")
    partiel = cible.with_suffix(cible.suffix + ".partiel")
    entetes = {"User-Agent": "projet-etudiant-tourisme-ferroviaire"}
    with requests.get(URL_LIGNES_SNCF, stream=True, timeout=(30, 600), headers=entetes) as r:
        r.raise_for_status()
        with partiel.open("wb") as f:
            for bloc in r.iter_content(chunk_size=1 << 20):
                f.write(bloc)
    partiel.replace(cible)
    print(f"    -> {cible.name} ({cible.stat().st_size / 1e6:.1f} Mo)")
    return cible


def _ligne_fermee(proprietes: dict) -> bool:
    """Vrai si le statut de la ligne dit qu'elle est fermée, déclassée, neutralisée ou déposée."""
    for champ, valeur in proprietes.items():
        if "mnemo" in champ.lower() or "statut" in champ.lower():
            return any(mot in normaliser(str(valeur)) for mot in STATUTS_FERMES)
    return False


def lire_lignes_sncf(chemin: Path, gares: pd.DataFrame | None = None) -> Reseau:
    """Construit le graphe à partir du GeoJSON SNCF. Avec `gares`, ne garde que les lignes de leur zone."""
    contenu = json.loads(chemin.read_text(encoding="utf-8"))
    zone = None
    if gares is not None and len(gares):
        zone = (
            float(gares["lat"].min()) - MARGE_DEG, float(gares["lat"].max()) + MARGE_DEG,
            float(gares["lon"].min()) - MARGE_DEG, float(gares["lon"].max()) + MARGE_DEG,
        )  # fmt: skip
    reseau = Reseau()
    for numero, forme in enumerate(contenu.get("features", [])):
        geometrie = forme.get("geometry") or {}
        if _ligne_fermee(forme.get("properties") or {}):
            continue
        # Une ligne est un seul trait (LineString) ou plusieurs morceaux (MultiLineString).
        morceaux = {"LineString": [geometrie.get("coordinates")], "MultiLineString": geometrie.get("coordinates")}
        for morceau in morceaux.get(geometrie.get("type")) or []:
            points = [(float(c[1]), float(c[0])) for c in morceau or []]  # le GeoJSON écrit (lon, lat)
            if zone and not any(zone[0] <= lat <= zone[1] and zone[2] <= lon <= zone[3] for lat, lon in points):
                continue
            # Deux points identiques au mètre près sont le même nœud : c'est ce qui relie les tronçons.
            noeuds = [(round(lat, 5), round(lon, 5)) for lat, lon in points]
            reseau.ajouter_voie(noeuds, points, ligne=numero)
    reseau.relier_les_extremites()
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


if __name__ == "__main__":
    import sys

    from app import config
    from ingestion import gares_sncf

    dossier_brut = config.DOSSIER_DONNEES / "brut"
    dossier_brut.mkdir(parents=True, exist_ok=True)
    try:
        if "--osm" in sys.argv:
            fichier_gares = sorted(dossier_brut.glob("gares-de-voyageurs*.json"))[0]
            gares_region, _ = gares_sncf.normaliser_gares(gares_sncf.lire_gares(fichier_gares))
            telecharger(gares_region, dossier_brut / "voies-osm.json")
        else:
            telecharger_lignes_sncf(dossier_brut / "lignes-sncf.geojson")
    except (RuntimeError, requests.RequestException) as echec:
        raise SystemExit(f"Échec : {echec}\nRelancer la même commande pour réessayer.")
    print("Voies téléchargées. Lancer maintenant : python -m ingestion.pipeline")
