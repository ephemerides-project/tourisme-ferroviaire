"""Petits outils de normalisation de texte, partagés par l'ingestion et l'IA."""

from __future__ import annotations

import re
import unicodedata


def sans_accents(texte: str) -> str:
    """« Chambéry » -> « Chambery »."""
    decompose = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in decompose if not unicodedata.combining(c))


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, ponctuation remplacée par des espaces.

    « Grenoble-Universités-Gières » -> « grenoble universites gieres »
    """
    texte = sans_accents(texte).lower()
    texte = re.sub(r"[^a-z0-9]+", " ", texte)
    return texte.strip()


def cle(texte: str) -> str:
    """Clé compacte pour comparer des noms de colonnes : « Code(s) UIC » -> « codesuic »."""
    return normaliser(texte).replace(" ", "")
