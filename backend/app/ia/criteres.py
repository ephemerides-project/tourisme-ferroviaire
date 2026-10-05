"""Critères de recherche : la structure commune entre la question de l'utilisateur et la base.

Que les critères viennent du LLM ou des règles, ils passent par ce modèle, qui
rejette toute valeur inconnue ou hors bornes. Le LLM ne peut donc rien « inventer »
d'autre que des valeurs que la recherche sait traiter.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.themes import THEMES


class Criteres(BaseModel):
    origine: str | None = Field(None, description="Ville ou gare de départ, telle qu'écrite par l'utilisateur")
    duree_max_min: int | None = Field(None, description="Temps de trajet maximal en train, en minutes")
    marche_max_min: int | None = Field(None, description="Marche maximale depuis la gare, en minutes")
    themes: list[str] = Field(default_factory=list, description=f"Parmi : {', '.join(THEMES)}")
    public: Literal["famille"] | None = Field(None, description="« famille » si des enfants sont du voyage")
    difficulte: Literal["facile", "moyen", "difficile"] | None = None

    @field_validator("themes", mode="before")
    @classmethod
    def _themes_connus(cls, valeur):
        """Ne garde que les thèmes connus de l'application, sans doublon."""
        if not isinstance(valeur, list):
            return []
        connus = []
        for theme in valeur:
            theme = str(theme).strip().lower()
            if theme in THEMES and theme not in connus:
                connus.append(theme)
        return connus

    @field_validator("duree_max_min", "marche_max_min", mode="before")
    @classmethod
    def _duree_plausible(cls, valeur, info):
        """Une durée absurde (négative, 3 jours...) est ignorée plutôt que de faire échouer la requête."""
        maximum = {"duree_max_min": 600, "marche_max_min": 180}[info.field_name]
        try:
            valeur = int(float(valeur))
        except (TypeError, ValueError):
            return None
        return valeur if 1 <= valeur <= maximum else None

    @field_validator("origine", mode="before")
    @classmethod
    def _origine_propre(cls, valeur):
        valeur = str(valeur).strip() if valeur else ""
        return valeur or None

    @field_validator("public", "difficulte", mode="before")
    @classmethod
    def _valeur_connue_ou_rien(cls, valeur, info):
        autorisees = {"public": {"famille"}, "difficulte": {"facile", "moyen", "difficile"}}[info.field_name]
        valeur = str(valeur).strip().lower() if valeur else ""
        return valeur if valeur in autorisees else None

    def themes_recherches(self) -> list[str]:
        """Thèmes utilisés pour interroger la base : un voyage en famille ajoute le thème « famille »."""
        themes = list(self.themes)
        if self.public == "famille" and "famille" not in themes:
            themes.append("famille")
        return themes

    def est_vide(self) -> bool:
        return not any(self.model_dump().values())


def fusionner(precedents: Criteres | None, nouveaux: Criteres) -> Criteres:
    """Mémoire de conversation : ce que dit le nouveau message remplace l'ancien, le reste est conservé.

    « ... à moins de 2 h de Grenoble, activité nature » puis « et si je préfère du culturel ? »
    -> origine et durée conservées, thèmes remplacés par [culture].
    """
    if precedents is None:
        return nouveaux
    fusion = precedents.model_dump()
    for champ, valeur in nouveaux.model_dump().items():
        if valeur:
            fusion[champ] = valeur
    # La difficulté portait sur l'activité précédente : elle ne survit pas à un changement de thème.
    if nouveaux.themes and not nouveaux.difficulte:
        fusion["difficulte"] = None
    return Criteres(**fusion)
