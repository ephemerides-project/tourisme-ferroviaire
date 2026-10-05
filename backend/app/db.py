"""Accès à la base : une connexion par requête HTTP, les lignes sont renvoyées en dictionnaires."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row

from app import config


def connexion() -> Iterator[psycopg.Connection]:
    """Dépendance FastAPI : ouvre la connexion, la ferme à la fin de la requête."""
    with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as conn:
        yield conn
