"""Client LLM minimal, compatible avec l'API « chat completions » d'OpenAI.

Ce format est accepté par la plupart des fournisseurs et des serveurs auto-hébergés
(Ollama, vLLM, Mistral, OpenAI...). Changer de modèle, ou passer du cloud au local,
revient donc à changer trois variables d'environnement : LLM_BASE_URL, LLM_MODEL, LLM_API_KEY.
C'est ce qui rend la comparaison cloud / auto-hébergé mesurable avec le même code.
"""

from __future__ import annotations

import json
import time

import requests

from app import config


class ErreurLLM(Exception):
    """Le LLM est injoignable ou sa réponse est inexploitable : l'appelant bascule sur le repli."""


def disponible() -> bool:
    return bool(config.LLM_BASE_URL and config.LLM_MODEL)


def completer_json(systeme: str, utilisateur: str) -> tuple[dict, dict]:
    """Envoie une consigne et un message, renvoie (objet JSON produit, mesures d'usage).

    Les mesures (durée, jetons) alimentent l'analyse de coûts et de temps de réponse.
    """
    if not disponible():
        raise ErreurLLM("Aucun LLM configuré")
    entetes = {"Content-Type": "application/json"}
    if config.LLM_API_KEY:
        entetes["Authorization"] = f"Bearer {config.LLM_API_KEY}"
    corps = {
        "model": config.LLM_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": systeme}, {"role": "user", "content": utilisateur}],
    }
    debut = time.perf_counter()
    try:
        reponse = requests.post(
            f"{config.LLM_BASE_URL}/chat/completions", headers=entetes, json=corps, timeout=config.LLM_TIMEOUT_S
        )
        reponse.raise_for_status()
        donnees = reponse.json()
        contenu = donnees["choices"][0]["message"]["content"]
    except (requests.RequestException, KeyError, IndexError, ValueError) as erreur:
        raise ErreurLLM(f"Appel au LLM impossible : {erreur}") from erreur

    usage = donnees.get("usage") or {}
    mesures = {
        "modele": config.LLM_MODEL,
        "duree_ms": round((time.perf_counter() - debut) * 1000),
        "jetons_entree": usage.get("prompt_tokens"),
        "jetons_sortie": usage.get("completion_tokens"),
    }
    return _lire_json(contenu), mesures


def _lire_json(contenu: str) -> dict:
    """Certains modèles entourent leur JSON de ```json ... ``` : on garde ce qui est entre accolades."""
    debut, fin = contenu.find("{"), contenu.rfind("}")
    if debut == -1 or fin <= debut:
        raise ErreurLLM("La réponse du LLM ne contient pas de JSON")
    try:
        objet = json.loads(contenu[debut : fin + 1])
    except json.JSONDecodeError as erreur:
        raise ErreurLLM(f"JSON invalide dans la réponse du LLM : {erreur}") from erreur
    if not isinstance(objet, dict):
        raise ErreurLLM("Le LLM n'a pas renvoyé un objet JSON")
    return objet
