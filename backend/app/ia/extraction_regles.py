"""Extraction des critères SANS LLM : expressions régulières et mots-clés.

Deux rôles :
- solution de repli quand le LLM est indisponible ou renvoie une réponse inexploitable ;
- point de comparaison pour mesurer ce que le LLM apporte réellement (voir evaluation/).
"""

from __future__ import annotations

import re

from app.ia.criteres import Criteres
from app.texte import normaliser, sans_accents

# thème -> radicaux cherchés dans la question (minuscules, sans accents)
MOTS_THEMES: dict[str, tuple[str, ...]] = {
    "nature": ("nature", "plein air", "foret", "cascade", "lac", "paysage", "verdure", "grand air"),
    "randonnee": ("randonn", "rando", "balade", "promenade", "sentier", "trek"),
    "montagne": ("montagne", "sommet", "alpin", "altitude", "ski"),
    "patrimoine": ("patrimoine", "chateau", "monument", "histoire", "historique", "eglise", "medieval", "vieille ville"),
    "culture": ("culture", "musee", "exposition", "expo", "theatre", "artistique"),
    "sport_loisirs": ("sport", "velo", "baignade", "escalade", "piscine", "loisir"),
    "gastronomie": ("restaurant", "gastronom", "manger", "degustation", "terroir", "bien manger"),
    "hebergement": ("hotel", "hebergement", "dormir", "camping", "nuit sur place"),
    "evenement": ("festival", "concert", "evenement", "spectacle"),
}
MOTS_FAMILLE = ("enfant", "famille", "poussette", "bambin", "petits")
MOTS_DIFFICULTE = {
    "facile": ("facile", "debutant", "tranquille", "accessible a tous"),
    "difficile": ("difficile", "sportif", "sportive", "engage"),
}
NOMBRES = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6}
_NB = r"\b(\d+|" + "|".join(NOMBRES) + ")"

# Durées, de la forme la plus précise à la plus générale. Chaque motif renvoie des minutes.
MOTIFS_DUREE: list[tuple[re.Pattern, callable]] = [
    (re.compile(r"\b(\d+)\s*h\s*(\d{1,2})\b"), lambda m: int(m[1]) * 60 + int(m[2])),  # 1h30, 1 h 30
    (re.compile(_NB + r"\s*heures?\s+et\s+demie?\b"), lambda m: _nombre(m[1]) * 60 + 30),  # une heure et demie
    (re.compile(_NB + r"\s*heures?\s*(\d{1,2})\b"), lambda m: _nombre(m[1]) * 60 + int(m[2])),  # 1 heure 30
    (re.compile(_NB + r"\s*(?:heures?|h)\b"), lambda m: _nombre(m[1]) * 60),  # 2 heures, 2h, une heure
    (re.compile(r"\b(?:une\s+)?demi[\s-]heure\b"), lambda m: 30),
    (re.compile(r"\b(?:un\s+)?quart\s+d\s?heure\b"), lambda m: 15),
    (re.compile(r"\b(\d+)\s*(?:minutes?|min|mn)\b"), lambda m: int(m[1])),  # 20 minutes, 20 min
]
MOTIF_MARCHE = re.compile(r"\b(march\w*|a pied)\b")
PORTEE_MARCHE = 30  # nombre de caractères max entre « marche » et la durée qu'il qualifie

# Prépositions qui introduisent une ville de départ, de la plus sûre à la plus ambiguë.
PREPOSITIONS = ("depuis", "au depart de", "a partir de", "en partant de", "autour de", "pres de", "de", "d")
# Premiers mots de noms de gares trop courants pour désigner une ville à eux seuls.
MOTS_TROP_COURANTS = {"saint", "sainte", "les", "le", "la", "pont", "mont", "port", "bourg", "val"}
MOTIF_NOM_PROPRE = re.compile(
    r"\b(?:depuis|au départ de|à partir de|en partant de|autour de|près de|de|d['’])\s*"
    r"((?:[A-ZÉÈÎ][\w'’-]+)(?:[ -](?:[A-ZÉÈÎ][\w'’-]+|les|le|la|en|sur|de|du))*)"
)


def _nombre(texte: str) -> int:
    return NOMBRES[texte] if texte in NOMBRES else int(texte)


def _durees(texte: str) -> tuple[int | None, int | None]:
    """Renvoie (durée de trajet, durée de marche), en minutes.

    Chaque mention de « marche », « marcher » ou « à pied » est rattachée à la durée
    la plus proche d'elle, de préférence sans ponctuation entre les deux.
    Les autres durées sont des temps de trajet.
    """
    durees: list[tuple[int, int, int]] = []  # (début, fin, minutes)
    for motif, en_minutes in MOTIFS_DUREE:
        for m in motif.finditer(texte):
            if not any(m.start() < fin and m.end() > debut for debut, fin, _ in durees):
                durees.append((m.start(), m.end(), en_minutes(m)))

    de_marche: set[int] = set()
    for mot in MOTIF_MARCHE.finditer(texte):
        ecarts = []
        for i, (debut, fin, _) in enumerate(durees):
            entre = texte[fin : mot.start()] if fin <= mot.start() else texte[mot.end() : debut]
            # Une virgule ou un point entre les deux : ils ne sont pas dans le même groupe de mots.
            autre_groupe = bool(re.search(r"[,;.:!?]", entre))
            ecarts.append((autre_groupe, len(entre), i))
        if ecarts and min(ecarts)[1] <= PORTEE_MARCHE:
            de_marche.add(min(ecarts)[2])

    marche = min((d[2] for i, d in enumerate(durees) if i in de_marche), default=None)
    trajet = min((d[2] for i, d in enumerate(durees) if i not in de_marche), default=None)
    return trajet, marche


def _origine(question: str, noms_gares: list[str]) -> str | None:
    """Ville de départ : un nom de gare connu précédé d'une préposition, sinon un nom propre."""
    texte = f" {normaliser(question)} "
    # 1. Nom de gare connu (ou son premier mot : « Chambéry » pour « Chambéry-Challes-les-Eaux »).
    meilleur: tuple[int, int, str] | None = None  # (rang de la préposition, -longueur, nom à renvoyer)
    for nom in noms_gares:
        complet = normaliser(nom)
        premier = complet.split(" ")[0]
        for candidat in {complet, premier}:
            if len(candidat) < 3 or (candidat != complet and candidat in MOTS_TROP_COURANTS):
                continue
            for rang, preposition in enumerate(PREPOSITIONS):
                if f" {preposition} {candidat} " in texte:
                    trouve = (rang, -len(candidat), nom if candidat == complet else candidat.capitalize())
                    if meilleur is None or trouve < meilleur:
                        meilleur = trouve
                    break
    if meilleur:
        return meilleur[2]
    # 2. Nom propre inconnu de la base : on le renvoie quand même, l'assistant signalera qu'il est introuvable.
    trouve = MOTIF_NOM_PROPRE.search(question)
    return trouve.group(1).strip() if trouve else None


def extraire(question: str, noms_gares: list[str] | None = None) -> Criteres:
    """Transforme une question en critères, sans aucun appel externe."""
    texte = normaliser(question)
    # normaliser() supprime la ponctuation ; pour les durées on garde un texte proche de l'original.
    texte_durees = sans_accents(question).lower().replace("’", " ").replace("'", " ")
    trajet, marche = _durees(texte_durees)

    themes = [theme for theme, mots in MOTS_THEMES.items() if any(re.search(rf"\b{mot}", texte) for mot in mots)]
    difficulte = next(
        (niveau for niveau, mots in MOTS_DIFFICULTE.items() if any(re.search(rf"\b{mot}", texte) for mot in mots)), None
    )
    return Criteres(
        origine=_origine(question, noms_gares or []),
        duree_max_min=trajet,
        marche_max_min=marche,
        themes=themes,
        public="famille" if any(re.search(rf"\b{mot}", texte) for mot in MOTS_FAMILLE) else None,
        difficulte=difficulte,
    )
