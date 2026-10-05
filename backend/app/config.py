"""Configuration centralisée, lue dans les variables d'environnement.

Un fichier `.env` placé à la racine du projet est chargé automatiquement
(voir `.env.exemple`). Les variables déjà définies dans l'environnement gardent la priorité.
"""

from __future__ import annotations

import os
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]  # dossier tourisme-ferroviaire/


def _charger_dotenv(chemin: Path) -> None:
    """Mini-lecteur de fichier .env : lignes `CLE=valeur`, `#` pour les commentaires."""
    if not chemin.exists():
        return
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, valeur = ligne.split("=", 1)
        os.environ.setdefault(cle.strip(), valeur.strip().strip('"').strip("'"))


_charger_dotenv(RACINE / ".env")


def _env(nom: str, defaut: str) -> str:
    return os.environ.get(nom, defaut)


# --- Base de données -------------------------------------------------------
DATABASE_URL = _env("DATABASE_URL", "postgresql://tourisme:tourisme@localhost:5432/tourisme")
SCHEMA_SQL = Path(_env("SCHEMA_SQL", str(RACINE / "db" / "schema.sql")))

# --- Périmètre géographique ------------------------------------------------
# Départements d'Auvergne-Rhône-Alpes. Réduire la liste pour un périmètre plus petit.
DEPARTEMENTS = tuple(d.strip() for d in _env("DEPARTEMENTS", "01,03,07,15,26,38,42,43,63,69,73,74").split(","))
# Boîte englobante de la région (lat_min, lat_max, lon_min, lon_max) : sert de garde-fou.
BOITE_REGION = (44.0, 46.9, 2.0, 7.3)
ORIGINE_PAR_DEFAUT = _env("ORIGINE_PAR_DEFAUT", "Grenoble")

# --- Hypothèses métier (toutes explicables en soutenance) -------------------
RAYON_POI_M = int(_env("RAYON_POI_M", "2000"))  # un POI est rattaché aux gares situées à moins de 2 km
VITESSE_MARCHE_M_MIN = 75.0  # 4,5 km/h
FACTEUR_DETOUR = 1.3  # un trajet à pied est ~30 % plus long que la ligne droite
MARGE_CORRESPONDANCE_MIN = 15  # temps forfaitaire ajouté pour une correspondance
DUREE_MAX_CORRESPONDANCE_MIN = 240  # on ne calcule pas de trajet à correspondance au-delà de 4 h
TYPES_ROUTE_GTFS = tuple(int(t) for t in _env("TYPES_ROUTE_GTFS", "2").split(","))  # 2 = train, 3 = car

# Valeurs utilisées quand l'utilisateur ne précise rien.
DUREE_MAX_PAR_DEFAUT_MIN = 120
MARCHE_MAX_PAR_DEFAUT_MIN = 25
NB_RECOMMANDATIONS = 5

# --- LLM (facultatif) ------------------------------------------------------
# Toute API compatible « OpenAI chat completions » convient : Ollama en local
# (http://localhost:11434/v1), Mistral, OpenAI, vLLM... Laisser LLM_BASE_URL vide
# pour fonctionner sans LLM (extraction par règles + réponses par gabarit).
LLM_BASE_URL = _env("LLM_BASE_URL", "").rstrip("/")
LLM_MODEL = _env("LLM_MODEL", "")
LLM_API_KEY = _env("LLM_API_KEY", "")
LLM_TIMEOUT_S = float(_env("LLM_TIMEOUT_S", "30"))

# --- Divers ----------------------------------------------------------------
CORS_ORIGINES = [o.strip() for o in _env("CORS_ORIGINES", "http://localhost:3000").split(",")]
DOSSIER_DONNEES = Path(_env("DOSSIER_DONNEES", str(RACINE / "donnees")))
