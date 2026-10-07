"""API de la plateforme. Lancer avec : `uvicorn app.main:app --reload` (depuis backend/).

Documentation interactive générée automatiquement : http://localhost:8000/docs
"""

from __future__ import annotations

from typing import Annotated

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import config
from app.db import connexion
from app.ia import assistant, llm
from app.ia.criteres import Criteres
from app.metier import destinations as metier_destinations
from app.metier import gares as metier_gares
from app.themes import THEMES

app = FastAPI(title="Tourisme ferroviaire — API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINES, allow_methods=["*"], allow_headers=["*"])

Connexion = Annotated[psycopg.Connection, Depends(connexion)]


def _themes_valides(themes: list[str]) -> list[str]:
    inconnus = [t for t in themes if t not in THEMES]
    if inconnus:
        raise HTTPException(422, f"Thèmes inconnus : {inconnus}. Valeurs possibles : {list(THEMES)}")
    return themes


def _gare_ou_404(conn: psycopg.Connection, gare_id: str) -> dict:
    gare = metier_gares.trouver_gare(conn, gare_id)
    if gare is None:
        raise HTTPException(404, f"Gare inconnue : {gare_id}")
    return gare


# --- Technique -------------------------------------------------------------
@app.get("/sante", tags=["technique"])
def sante(conn: Connexion) -> dict:
    """Vérifie que l'API et la base répondent, et indique si un LLM est configuré."""
    conn.execute("SELECT 1")
    return {"statut": "ok", "llm": config.LLM_MODEL if llm.disponible() else None}


@app.get("/stats", tags=["technique"])
def stats(conn: Connexion) -> dict:
    """Volumes réellement chargés en base et journal des imports."""
    return metier_gares.statistiques(conn)


# --- Explorer --------------------------------------------------------------
@app.get("/themes", tags=["explorer"])
def themes() -> list[dict]:
    return [{"id": identifiant, "libelle": libelle} for identifiant, libelle in THEMES.items()]


@app.get("/gares", tags=["explorer"])
def gares(conn: Connexion, q: str | None = None, toutes: bool = False) -> list[dict]:
    """Gares de la région. `q` filtre sur le nom ; `toutes=true` inclut les gares sans desserte connue."""
    return metier_gares.lister_gares(conn, q, desservies_seulement=not toutes)


@app.get("/gares/{gare_id}", tags=["explorer"])
def gare(conn: Connexion, gare_id: str) -> dict:
    return _gare_ou_404(conn, gare_id)


@app.get("/gares/{gare_id}/services", tags=["explorer"])
def services_de_la_gare(conn: Connexion, gare_id: str) -> list[dict]:
    """Services et accès de la gare : assistance PMR, vélo, cars, équipements proches."""
    _gare_ou_404(conn, gare_id)
    return metier_gares.services_des_gares(conn, [gare_id])[gare_id]


@app.get("/gares/{gare_id}/poi", tags=["explorer"])
def poi_de_la_gare(
    conn: Connexion,
    gare_id: str,
    theme: Annotated[list[str], Query()] = [],
    marche_max: Annotated[int | None, Query(ge=1, le=180)] = None,
) -> list[dict]:
    """Points d'intérêt à distance de marche d'une gare, filtrables par thème."""
    _gare_ou_404(conn, gare_id)
    return metier_gares.poi_proches(conn, gare_id, _themes_valides(theme), marche_max)


@app.get("/destinations", tags=["explorer"])
def destinations(
    conn: Connexion,
    origine: str,
    duree_max: Annotated[int, Query(ge=5, le=600)] = config.DUREE_MAX_PAR_DEFAUT_MIN,
    marche_max: Annotated[int, Query(ge=1, le=180)] = config.MARCHE_MAX_PAR_DEFAUT_MIN,
    theme: Annotated[list[str], Query()] = [],
    limite: Annotated[int, Query(ge=1, le=50)] = config.NB_RECOMMANDATIONS,
) -> dict:
    """Destinations accessibles depuis une gare (identifiant ou nom), classées. Aucun LLM."""
    depart = metier_gares.trouver_gare(conn, origine) or metier_gares.resoudre_gare(conn, origine)
    if depart is None:
        raise HTTPException(404, f"Gare de départ introuvable : {origine}")
    resultats, diagnostic = metier_destinations.rechercher(
        conn, depart["id"], duree_max, _themes_valides(theme), marche_max, limite
    )
    return {
        "origine": {k: depart[k] for k in ("id", "nom", "lat", "lon")},
        "destinations": resultats,
        "diagnostic": diagnostic,
    }


# --- Demander --------------------------------------------------------------
class Demande(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    contexte: Criteres | None = Field(None, description="Critères renvoyés par la réponse précédente (mémoire de session)")
    gare_selectionnee: str | None = Field(None, description="Identifiant de la gare sélectionnée sur la carte")
    utiliser_llm: bool = Field(True, description="Mettre à false pour comparer avec l'extraction par règles")


@app.post("/recherche", tags=["demander"])
def recherche(conn: Connexion, demande: Demande) -> dict:
    """Recherche en langage naturel : critères, destinations classées, explications."""
    return assistant.repondre(
        conn, demande.question.strip(), demande.contexte, demande.gare_selectionnee, demande.utiliser_llm
    )
