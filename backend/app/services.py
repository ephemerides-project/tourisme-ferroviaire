"""Services et accès d'une gare : la liste fermée affichée dans l'interface.

Chaque service a un code interne, un libellé, et une source :
- six fichiers SNCF Open Data (assistance PMR, équipements d'accessibilité, ascenseurs,
  stationnement vélo sécurisé, points de vente, Wi-Fi) ;
- les horaires GTFS (une gare desservie par des cars TER) ;
- les équipements DATAtourisme situés tout près de la gare (parking, taxis, arrêt de bus...).
"""

from __future__ import annotations

# code -> libellé. L'ordre est celui de l'affichage.
SERVICES: dict[str, str] = {
    "pmr": "Assistance aux personnes à mobilité réduite",
    "accessibilite": "Équipements d'accessibilité",
    "ascenseur": "Ascenseurs",
    "velo": "Stationnement vélo sécurisé",
    "car": "Cars TER",
    "bus": "Arrêt de bus à proximité",
    "parking": "Parking à proximité",
    "taxi": "Taxis à proximité",
    "covoiturage": "Aire de covoiturage à proximité",
    "recharge": "Borne de recharge électrique à proximité",
    "billets": "Vente de billets",
    "wifi": "Wi-Fi",
    "toilettes": "Toilettes publiques à proximité",
    "eau": "Point d'eau à proximité",
}

# Un équipement DATAtourisme compte pour la gare s'il est à moins de 400 m.
RAYON_SERVICE_M = 400

# type DATAtourisme (en minuscules) -> code de service
TYPES_DATATOURISME: dict[str, str] = {
    "busstation": "bus",
    "busstop": "bus",
    "parking": "parking",
    "taxistation": "taxi",
    "carpoolarea": "covoiturage",
    "electricvehiclechargingpoint": "recharge",
    "electricbyciclechargingpoint": "recharge",  # faute d'orthographe d'origine dans DATAtourisme
    "publiclavatories": "toilettes",
    "watersource": "eau",
}
