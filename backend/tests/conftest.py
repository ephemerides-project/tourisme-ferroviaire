"""Configuration commune des tests.

Les tests « unitaires » tournent sans base ni réseau.
Les tests marqués `base` ont besoin d'une base PostGIS dédiée, désignée par la variable
DATABASE_URL_TEST. ATTENTION : son contenu est remplacé par le jeu d'essai à chaque exécution.
Ne jamais y mettre l'adresse de la base qui contient les vraies données.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from psycopg.rows import dict_row

from app import config

DOSSIER_EXEMPLE = config.RACINE / "donnees" / "exemple"
URL_TEST = os.environ.get("DATABASE_URL_TEST")


@pytest.fixture(scope="session")
def base_chargee():
    """Charge le jeu d'essai dans la base de test, une fois pour toute la session."""
    if not URL_TEST:
        pytest.skip("DATABASE_URL_TEST non définie : tests avec base ignorés")
    from ingestion import pipeline

    ancienne = config.DATABASE_URL
    config.DATABASE_URL = URL_TEST
    try:
        bilan = pipeline.executer(DOSSIER_EXEMPLE, journal=lambda _message: None)
        yield bilan
    finally:
        config.DATABASE_URL = ancienne


@pytest.fixture()
def conn(base_chargee):
    with psycopg.connect(URL_TEST, row_factory=dict_row) as connexion:
        yield connexion


@pytest.fixture()
def sans_llm(monkeypatch):
    """Garantit qu'aucun LLM n'est configuré, quel que soit le .env de la machine."""
    monkeypatch.setattr(config, "LLM_BASE_URL", "")
    monkeypatch.setattr(config, "LLM_MODEL", "")
