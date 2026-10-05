"""Horaires théoriques — source : GTFS SNCF (transport.data.gouv.fr).

À partir des horaires, on calcule pour chaque couple de gares de la région :
- la durée médiane des trajets directs ;
- le nombre moyen de trajets directs par jour.

C'est ce qui permet de répondre à « quelles gares sont à moins de 1h30 de Grenoble ? »
sans appeler de service externe.
"""

from __future__ import annotations

import io
import math
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

FICHIERS = ("stops", "stop_times", "trips", "routes", "calendar", "calendar_dates")
RAYON_RATTACHEMENT_M = 300  # distance max pour rattacher un arrêt GTFS à une gare par proximité


def lire_gtfs(source: Path) -> dict[str, pd.DataFrame]:
    """Lit un GTFS (archive .zip ou dossier). Tout est lu en texte pour ne rien déformer."""
    tables: dict[str, pd.DataFrame] = {}
    if source.is_dir():
        for nom in FICHIERS:
            chemin = source / f"{nom}.txt"
            if chemin.exists():
                tables[nom] = pd.read_csv(chemin, dtype=str, encoding="utf-8-sig")
    else:
        with zipfile.ZipFile(source) as archive:
            presents = {Path(n).name: n for n in archive.namelist()}
            for nom in FICHIERS:
                if f"{nom}.txt" in presents:
                    contenu = archive.read(presents[f"{nom}.txt"])
                    tables[nom] = pd.read_csv(io.BytesIO(contenu), dtype=str, encoding="utf-8-sig")
    manquants = [n for n in ("stops", "stop_times", "trips") if n not in tables]
    if manquants:
        raise ValueError(f"GTFS incomplet, fichiers manquants : {manquants}")
    return tables


def heure_en_minutes(heures: pd.Series) -> pd.Series:
    """« 08:15:00 » -> 495. Le GTFS autorise « 25:10:00 » pour un passage après minuit."""
    morceaux = heures.str.split(":", expand=True)
    if morceaux.shape[1] < 2:
        return pd.Series(np.nan, index=heures.index)
    h = pd.to_numeric(morceaux[0], errors="coerce")
    m = pd.to_numeric(morceaux[1], errors="coerce")
    return h * 60 + m


def uic_depuis_stop_id(stop_id: str) -> str | None:
    """« StopPoint:OCETrain TER-87747006 » ou « StopArea:OCE87747006 » -> « 87747006 »."""
    trouve = re.search(r"(\d{8})$", str(stop_id))
    return trouve.group(1) if trouve else None


def _distances_m(lat1, lon1, lat2, lon2):
    """Distance de Haversine en mètres (vectorisée numpy)."""
    lat1, lon1, lat2, lon2 = (np.radians(x) for x in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * np.arcsin(np.sqrt(a))


def rattacher_arrets(stops: pd.DataFrame, gares: pd.DataFrame) -> tuple[dict[str, str], dict]:
    """Associe chaque arrêt GTFS à une gare du référentiel.

    1. par code UIC (présent à la fin du stop_id SNCF) ;
    2. à défaut, par proximité : la gare la plus proche à moins de 300 m.
    Les arrêts situés hors de la région ne sont rattachés à rien, c'est voulu.
    """
    uic_vers_gare = {uic: gare.id for gare in gares.itertuples() for uic in gare.codes_uic}
    correspondance: dict[str, str] = {}
    bilan = {"arrets": len(stops), "par_uic": 0, "par_proximite": 0}
    lat_g = gares["lat"].to_numpy(dtype=float)
    lon_g = gares["lon"].to_numpy(dtype=float)
    ids_g = gares["id"].to_numpy()
    for arret in stops.itertuples():
        gare_id = uic_vers_gare.get(uic_depuis_stop_id(arret.stop_id) or "")
        if gare_id:
            correspondance[arret.stop_id] = gare_id
            bilan["par_uic"] += 1
            continue
        try:
            lat, lon = float(arret.stop_lat), float(arret.stop_lon)
        except (TypeError, ValueError, AttributeError):
            continue
        if len(ids_g) == 0 or math.isnan(lat) or math.isnan(lon):
            continue
        distances = _distances_m(lat, lon, lat_g, lon_g)
        plus_proche = int(np.argmin(distances))
        if distances[plus_proche] <= RAYON_RATTACHEMENT_M:
            correspondance[arret.stop_id] = ids_g[plus_proche]
            bilan["par_proximite"] += 1
    bilan["rattaches"] = len(correspondance)
    return correspondance, bilan


def _jours_par_service(tables: dict[str, pd.DataFrame]) -> tuple[pd.Series, int]:
    """Nombre de jours de circulation de chaque service_id, et nombre total de jours couverts."""
    dates_par_service: dict[str, set[str]] = {}
    if "calendar" in tables:
        jours = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for ligne in tables["calendar"].itertuples():
            actifs = {i for i, j in enumerate(jours) if str(getattr(ligne, j, "0")) == "1"}
            periode = pd.date_range(ligne.start_date, ligne.end_date)
            dates_par_service[ligne.service_id] = {d.strftime("%Y%m%d") for d in periode if d.weekday() in actifs}
    if "calendar_dates" in tables:
        for ligne in tables["calendar_dates"].itertuples():
            dates = dates_par_service.setdefault(ligne.service_id, set())
            if str(ligne.exception_type) == "1":
                dates.add(ligne.date)
            else:
                dates.discard(ligne.date)
    toutes = set().union(*dates_par_service.values()) if dates_par_service else set()
    jours_service = pd.Series({s: len(d) for s, d in dates_par_service.items()}, dtype=float)
    return jours_service, max(len(toutes), 1)


def calculer_liaisons(
    tables: dict[str, pd.DataFrame], arret_vers_gare: dict[str, str], types_route: tuple[int, ...] = (2,)
) -> pd.DataFrame:
    """Liaisons directes entre gares : colonnes origine_id, destination_id, duree_min, trajets_jour."""
    trips = tables["trips"]
    if "routes" in tables and "route_type" in tables["routes"].columns:
        routes_ok = tables["routes"].loc[
            pd.to_numeric(tables["routes"]["route_type"], errors="coerce").isin(types_route), "route_id"
        ]
        trips = trips[trips["route_id"].isin(routes_ok)]

    # 1. Passages aux arrêts, limités aux gares de la région.
    passages = tables["stop_times"][["trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time"]].copy()
    passages = passages[passages["trip_id"].isin(trips["trip_id"])]
    passages["gare_id"] = passages["stop_id"].map(arret_vers_gare)
    passages = passages.dropna(subset=["gare_id"])
    passages["arrivee"] = heure_en_minutes(passages["arrival_time"])
    passages["depart"] = heure_en_minutes(passages["departure_time"])
    passages["ordre"] = pd.to_numeric(passages["stop_sequence"], errors="coerce")
    passages = passages.dropna(subset=["arrivee", "depart", "ordre"])[["trip_id", "gare_id", "ordre", "arrivee", "depart"]]

    # 2. Tous les couples (montée, descente) d'un même train.
    couples = passages.merge(passages, on="trip_id", suffixes=("_o", "_d"))
    couples = couples[(couples["ordre_o"] < couples["ordre_d"]) & (couples["gare_id_o"] != couples["gare_id_d"])]
    couples["duree"] = couples["arrivee_d"] - couples["depart_o"]
    couples = couples[couples["duree"] > 0]
    if couples.empty:
        return pd.DataFrame(columns=["origine_id", "destination_id", "duree_min", "trajets_jour"])

    # 3. Fréquence : nombre de jours où chaque train circule, rapporté à la période couverte.
    jours_service, nb_jours = _jours_par_service(tables)
    service_du_trip = trips.set_index("trip_id")["service_id"]
    couples["jours"] = couples["trip_id"].map(service_du_trip).map(jours_service).fillna(1.0)

    # 4. Agrégation par couple de gares.
    liaisons = (
        couples.groupby(["gare_id_o", "gare_id_d"])
        .agg(duree_min=("duree", "median"), jours=("jours", "sum"))
        .reset_index()
        .rename(columns={"gare_id_o": "origine_id", "gare_id_d": "destination_id"})
    )
    liaisons["duree_min"] = liaisons["duree_min"].round().astype(int)
    liaisons["trajets_jour"] = (liaisons["jours"] / nb_jours).round(2)
    return liaisons[["origine_id", "destination_id", "duree_min", "trajets_jour"]]
