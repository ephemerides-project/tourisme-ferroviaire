"""Services en gare — sources : SNCF Open Data et horaires GTFS.

Chaque fichier SNCF est facultatif : absent, il donne simplement moins de services.
Le rattachement à nos gares dépend de ce que le fichier fournit :
- un code UIC : assistance PMR, équipements d'accessibilité, points de vente ;
- le code à trois lettres ou le nom de la gare : stationnement vélo, Wi-Fi ;
- seulement une position : ascenseurs, rattachés à la gare située à moins de 400 m.
Les cars TER viennent du GTFS : les gares où s'arrête au moins une ligne de car.

Les équipements proches (parking, taxis, arrêt de bus...) sont ajoutés plus tard, en SQL,
à partir des points DATAtourisme déjà chargés : voir `charger.enrichir`.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from app.texte import normaliser
from ingestion.gtfs import _distances_m

COLONNES = ["gare_id", "code", "detail", "source"]
SOURCE = "SNCF Open Data"
TYPE_ROUTE_CAR = 3  # dans un GTFS, 3 = bus ou car
RAYON_ASCENSEUR_M = 400


def _lire(chemin: Path) -> list[dict]:
    """Un export JSON de SNCF Open Data est une liste d'enregistrements."""
    contenu = json.loads(chemin.read_text(encoding="utf-8"))
    return contenu if isinstance(contenu, list) else contenu.get("results", [])


def _par_uic(gares: pd.DataFrame) -> dict[str, str]:
    return {uic: g.id for g in gares.itertuples() for uic in g.codes_uic}


def _par_nom(gares: pd.DataFrame) -> dict[str, str]:
    return {normaliser(g.nom): g.id for g in gares.itertuples()}


def _uic(valeur) -> str:
    """« 0087747006 » ou 87747006 -> « 87747006 »."""
    return str(valeur or "")[-8:]


def assistance_pmr(enregistrements: list[dict], gares: pd.DataFrame) -> list[tuple]:
    """Gares où SNCF assure l'assistance aux personnes handicapées ou à mobilité réduite."""
    uic_vers_gare = _par_uic(gares)
    lignes = []
    for e in enregistrements:
        gare_id = uic_vers_gare.get(_uic(e.get("code_uic")))
        if not gare_id:
            continue
        prise_en_charge = str(e.get("typepriseencharge") or "").upper()
        detail = "Avec ou sans réservation" if "SPONTANE" in prise_en_charge else "Sur réservation"
        if e.get("lieurendezvousgare"):
            detail += f". Rendez-vous : {str(e['lieurendezvousgare']).strip()}"
        lignes.append((gare_id, "pmr", detail, SOURCE))
    return lignes


def equipements_accessibilite(enregistrements: list[dict], gares: pd.DataFrame) -> list[tuple]:
    """Équipements d'accessibilité de chaque gare (boucle magnétique, bandes d'éveil, information sonore...)."""
    uic_vers_gare = _par_uic(gares)
    par_gare: dict[str, set[str]] = {}
    for e in enregistrements:
        gare_id = uic_vers_gare.get(_uic(e.get("uic")))
        if gare_id and e.get("accessibilite"):
            par_gare.setdefault(gare_id, set()).add(str(e["accessibilite"]).strip())
    return [(gare_id, "accessibilite", " · ".join(sorted(libelles)), SOURCE) for gare_id, libelles in par_gare.items()]


def ascenseurs(enregistrements: list[dict], gares: pd.DataFrame) -> list[tuple]:
    """Ascenseurs par gare, avec le nombre d'appareils en panne au moment du téléchargement.

    Le fichier ne donne ni code UIC ni nom de gare : chaque appareil est rattaché par sa position.
    """
    lat_g, lon_g, ids_g = gares["lat"].to_numpy(float), gares["lon"].to_numpy(float), gares["id"].to_numpy()
    compte: dict[str, list[int]] = {}  # gare -> [nombre d'ascenseurs, dont en panne]
    for e in enregistrements:
        if not str(e.get("libelle") or "").upper().startswith("ASC"):
            continue  # le fichier contient aussi les escaliers mécaniques
        try:
            lat, lon = (float(v) for v in str(e.get("position_geographique")).split(","))
        except ValueError:
            continue
        distances = _distances_m(lat, lon, lat_g, lon_g)
        plus_proche = int(np.argmin(distances))
        if distances[plus_proche] <= RAYON_ASCENSEUR_M:
            total = compte.setdefault(ids_g[plus_proche], [0, 0])
            total[0] += 1
            total[1] += str(e.get("etat_de_fonctionnement") or "").upper() == "KO"
    lignes = []
    for gare_id, (nombre, en_panne) in compte.items():
        detail = f"{nombre} ascenseur{'s' if nombre > 1 else ''}"
        if en_panne:
            detail += f", dont {en_panne} en panne au dernier relevé"
        lignes.append((gare_id, "ascenseur", detail, SOURCE))
    return lignes


def velos(enregistrements: list[dict], gares: pd.DataFrame) -> list[tuple]:
    """Gares disposant de places de stationnement vélo sécurisé."""
    par_trigramme = {str(g.trigramme).upper(): g.id for g in gares.itertuples() if g.trigramme}
    par_nom = _par_nom(gares)
    lignes = []
    for e in enregistrements:
        gare_id = par_trigramme.get(str(e.get("code_gare") or "").upper()) or par_nom.get(
            normaliser(str(e.get("nom_de_la_gare") or ""))
        )
        # Le fichier porte un compte par date de relevé (nombre_places_au_06_24, ..._12_24) : on prend le plus grand.
        places = max((v for c, v in e.items() if c.startswith("nombre_places") and isinstance(v, (int, float))), default=0)
        if gare_id and places > 0:
            pluriel = "s" if places > 1 else ""
            lignes.append((gare_id, "velo", f"{int(places)} place{pluriel} sécurisée{pluriel}", SOURCE))
    return lignes


def points_de_vente(enregistrements: list[dict], gares: pd.DataFrame) -> list[tuple]:
    """Guichets et automates de vente de billets."""
    uic_vers_gare = _par_uic(gares)
    par_gare: dict[str, set[str]] = {}
    for e in enregistrements:
        gare_id = uic_vers_gare.get(_uic(e.get("gare_code_uic")))
        type_de_vente = normaliser(str(e.get("type_de_point_de_vente") or ""))
        if gare_id and type_de_vente:
            libelle = "Guichet" if "guichet" in type_de_vente else "Automate" if "automate" in type_de_vente else "Autre point de vente"
            par_gare.setdefault(gare_id, set()).add(libelle)
    return [(gare_id, "billets", " · ".join(sorted(types)), SOURCE) for gare_id, types in par_gare.items()]


def wifi(enregistrements: list[dict], gares: pd.DataFrame) -> list[tuple]:
    """Gares équipées du Wi-Fi. Le fichier ne donne que le nom de la gare : rattachement par le nom."""
    par_nom = _par_nom(gares)
    trouvees = {par_nom.get(normaliser(str(e.get("nom") or ""))) for e in enregistrements}
    return [(gare_id, "wifi", "Wi-Fi gratuit", SOURCE) for gare_id in sorted(g for g in trouvees if g)]


def cars(tables: dict[str, pd.DataFrame], arret_vers_gare: dict[str, str]) -> list[tuple]:
    """Gares où s'arrête au moins une ligne de car, d'après les horaires GTFS."""
    if "routes" not in tables or "route_type" not in tables["routes"].columns:
        return []
    routes = tables["routes"]
    routes_car = routes.loc[pd.to_numeric(routes["route_type"], errors="coerce") == TYPE_ROUTE_CAR, "route_id"]
    trajets = tables["trips"].loc[tables["trips"]["route_id"].isin(routes_car), "trip_id"]
    passages = tables["stop_times"]
    arrets = passages.loc[passages["trip_id"].isin(trajets), "stop_id"].unique()
    gares = sorted({arret_vers_gare[a] for a in arrets if a in arret_vers_gare})
    return [(gare_id, "car", "Arrêt de car dans les horaires SNCF", "GTFS SNCF") for gare_id in gares]


# fichier local -> fonction qui le lit
LECTEURS = {
    "assistance-pmr.json": assistance_pmr,
    "equipements-accessibilite.json": equipements_accessibilite,
    "ascenseurs.json": ascenseurs,
    "velos-en-gare.json": velos,
    "points-de-vente.json": points_de_vente,
    "wifi-en-gare.json": wifi,
}


def rassembler(dossier: Path, gares: pd.DataFrame, tables: dict, arret_vers_gare: dict) -> tuple[pd.DataFrame, dict]:
    """Tous les services connus, une ligne par (gare, service). Renvoie aussi le nombre de gares par service."""
    lignes = cars(tables, arret_vers_gare)
    for fichier, lecteur in LECTEURS.items():
        if (dossier / fichier).exists():
            lignes += lecteur(_lire(dossier / fichier), gares)
    services = pd.DataFrame(lignes, columns=COLONNES).drop_duplicates(["gare_id", "code"])
    return services, services["code"].value_counts().to_dict()
