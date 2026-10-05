"""Correspondance entre les types DATAtourisme et nos thèmes internes.

DATAtourisme décrit chaque point d'intérêt par une liste de types issus de son
ontologie (ex. `WalkingTour`, `Museum`, `NaturalHeritage`). L'application, elle,
raisonne sur une dizaine de thèmes simples. Ce fichier fait le pont.

La règle est volontairement simple : un thème est attribué dès qu'un de ses
mots-clés apparaît dans le nom d'un type. Le pipeline affiche les types restés
sans thème pour que la table puisse être complétée.
"""

from __future__ import annotations

import re

from app.texte import normaliser

# Libellés affichés dans l'interface et transmis au LLM.
THEMES: dict[str, str] = {
    "nature": "Nature",
    "randonnee": "Randonnée",
    "montagne": "Montagne",
    "patrimoine": "Patrimoine",
    "culture": "Culture",
    "famille": "Famille",
    "sport_loisirs": "Sport et loisirs",
    "gastronomie": "Gastronomie",
    "hebergement": "Hébergement",
    "evenement": "Événement",
}

# thème -> mots-clés cherchés (en minuscules) dans le nom du type.
MOTS_CLES: dict[str, tuple[str, ...]] = {
    "randonnee": ("walkingtour", "hiking", "trail", "pedestrian"),
    "nature": (
        "naturalheritage", "parkandgarden", "garden", "lake", "waterfall", "cave", "forest",
        "pointofview", "river", "naturereserve", "naturalpark", "gorge", "canyon", "wetland", "landform",
    ),
    "montagne": ("ski", "mountain", "refuge", "wintersport", "summit", "glacier", "snow", "nordic"),
    "patrimoine": (
        "castle", "church", "cathedral", "abbey", "chapel", "religioussite", "remarkablebuilding",
        "archeologicalsite", "remembrancesite", "culturalheritage", "cityheritage", "technicalheritage",
        "monument", "palace", "fort", "bridge", "mill", "ruins", "tower",
    ),
    "culture": (
        "museum", "culturalsite", "theater", "cinema", "library", "gallery", "interpretationcentre",
        "artist", "concert", "exhibition", "showevent", "culturalevent",
    ),
    "famille": (
        "themepark", "zoo", "animalpark", "teachingfarm", "playground", "children", "minigolf",
        "aquarium", "leisurecomplex", "treeclimbing", "amusement",
    ),
    "sport_loisirs": (
        "sportsandleisureplace", "sport", "leisure", "swimming", "beach", "climbing", "golf", "tennis",
        "cyclingtour", "horsetour", "equestrian", "nautical", "bowling", "skating", "fluvialtour",
        "activityprovider",
    ),
    "gastronomie": (
        "restaurant", "foodestablishment", "tasting", "winery", "cellar", "brewery", "bistro",
        "cafe", "localproducer", "farmproduce","localproductsshop",
    ),
    "hebergement": (
        "accommodation", "hotel", "camping", "guesthouse", "hostel", "rental", "holidayresort",
        "bedandbreakfast", "collectiveaccommodation", "lodging",
    ),
    "evenement": ("entertainmentandevent", "festival", "saleevent", "socialevent", "sportsevent", "event"),
}

# Types reconnus par leur nom EXACT : un mot-clé serait trop large (« park » attraperait « ParkingLot »).
TYPES_EXACTS: dict[str, str] = {"park": "nature", "practice": "sport_loisirs"}

# Types trop génériques pour dire quoi que ce soit : ignorés sans avertissement.
TYPES_GENERIQUES = {
    "pointofinterest", "placeofinterest", "product", "tour", "thing",
    "localbusiness", "orderedlist", "serviceprovider",
}

# Types connus, volontairement laissés sans thème : ce ne sont pas des buts de sortie.
# À revoir en équipe (un marché ou un artisan peuvent mériter un thème).
TYPES_SANS_THEME = {
    "store",
    "craftsmanshop",
    "touristinformationcenter",
    "convenientservice",
    "conference",
    "localtouristoffice",
    "medicalplace",
    "electricvehiclechargingpoint",
    "healthcareprofessional",
    "taxistation",
    "taxicompany",
    "pharmacy",
    "parking",
    "touroperatorortravelagency",
    "equipmentrepairshop",
    "incomingtravelagency",
    "antiqueandsecondhandgooddealer",
    "trainstation",
}

# Thèmes proposés quand la demande n'en précise aucun : des activités, pas des services.
# Les événements sont écartés par défaut car leurs dates ne sont pas contrôlées.
THEMES_ACTIVITE = tuple(theme for theme in THEMES if theme not in ("hebergement", "evenement"))

# Faux amis : « Transport » contient « sport », on écarte donc ces types avant de chercher.
MOTS_EXCLUS = ("transport",)


def nom_local(type_source: str) -> str:
    """Garde la fin d'une URI : `https://www.datatourisme.fr/ontology/core#Museum` -> `Museum`."""
    fin = type_source.strip().rsplit("#", 1)[-1].rsplit("/", 1)[-1]
    return fin.split(":")[-1]  # gère aussi la forme préfixée `schema:Museum`


def classer(types_source: list[str]) -> list[str]:
    """Renvoie la liste triée des thèmes internes correspondant aux types fournis."""
    trouves: set[str] = set()
    for type_source in types_source:
        nom = nom_local(type_source).lower()
        if nom in TYPES_GENERIQUES or any(mot in nom for mot in MOTS_EXCLUS):
            continue
        if nom in TYPES_EXACTS:
            trouves.add(TYPES_EXACTS[nom])
        for theme, mots in MOTS_CLES.items():
            if any(mot in nom for mot in mots):
                trouves.add(theme)
    return sorted(trouves)


def est_classe(type_source: str) -> bool:
    """Vrai si le type est générique, volontairement sans thème, ou rattaché à un thème."""
    nom = nom_local(type_source).lower()
    if nom in TYPES_GENERIQUES or nom in TYPES_SANS_THEME or any(mot in nom for mot in MOTS_EXCLUS):
        return True
    return bool(classer([type_source]))


# --- Enrichissement par le texte ------------------------------------------
# Certains thèmes ne correspondent à aucun type DATAtourisme (« montagne », « famille »).
# On les déduit donc aussi de quelques mots du nom et de la description. C'est une
# heuristique simple, à remplacer plus tard par une recherche sémantique (embeddings).
MOTS_CLES_TEXTE: dict[str, re.Pattern] = {
    "montagne": re.compile(
        r"\b(montagne|alpage|sommet|massif|refuge|alpin|alpine|altitude)\b"
    ),
    "randonnee": re.compile(r"\b(randonnee|randonnees|sentier|sentiers)\b"),
    "famille": re.compile(r"\b(enfant|enfants|famille|familial|familiale|ludique)\b"),
    "gastronomie": re.compile(
        r"\b(degustation|degustations|vin|vins|vigneron|vignerons|fromage|fromages|gourmand|gourmande)\b"
    ),
}
# Un hôtel « face à la montagne » n'est pas une activité de montagne : on n'enrichit pas ces POI.
THEMES_DE_SERVICE = {"hebergement", "gastronomie", "evenement"}


def enrichir_par_texte(themes: list[str], nom: str, description: str | None) -> list[str]:
    """Ajoute les thèmes repérés dans le texte, sauf pour les POI de pur service."""
    if themes and set(themes) <= THEMES_DE_SERVICE:
        return themes
    texte = normaliser(f"{nom} {description or ''}")
    ajoutes = {theme for theme, motif in MOTS_CLES_TEXTE.items() if motif.search(texte)}
    return sorted(set(themes) | ajoutes)
