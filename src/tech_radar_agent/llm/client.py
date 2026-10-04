"""Client générique pour tout serveur qui parle le format OpenAI chat completions (ADR 0008).

Ce module connaît HTTP et le format de réponse. Il ne sait RIEN du scoring, des résumés ni de
ton profil d'intérêts : tout ça vit dans un autre module, qui reçoit un LlmClient.

Requête (ce que le serveur attend) :
    POST {base_url}/chat/completions
    Authorization: Bearer <api_key>          <- seulement s'il y a une clé
    Corps JSON : {"model": "...", "messages": [...], ...champs optionnels}

Réponse (ce qu'on reçoit, simplifiée) :
    {"choices": [{"message": {"role": "assistant", "content": "la réponse"}}],
     "usage": {"prompt_tokens": 48, "completion_tokens": 2, ...}}

SQUELETTE : remplace chaque `raise NotImplementedError` et chaque TODO. Supprime ces commentaires
guides au fur et à mesure (garde ceux qui expliquent *pourquoi*).
⚠️ Commentaires temporairement en français : à repasser en anglais à la fin de l'exercice.
"""

import logging
from typing import Any

import httpx

from tech_radar_agent.llm.settings import LlmSettings

logger = logging.getLogger(__name__)

# Un message de la conversation : {"role": "system" | "user" | "assistant", "content": "..."}.
Message = dict[str, str]

# Le délai d'attente et reasoning_effort ne sont PAS des constantes ici : ils viennent de LlmSettings
# (variables LLM_REQUEST_TIMEOUT et LLM_REASONING_EFFORT, voir .env.example), pour s'adapter à l'environnement.
#   settings.request_timeout : float, 30 par défaut
#   settings.reasoning_effort : str ou None (None = ne pas envoyer le champ)


class LlmError(Exception):
    """Le LLM n'a pas pu fournir de réponse exploitable.

    Un seul type d'erreur pour tous les échecs (réseau, délai dépassé, code HTTP, réponse inattendue),
    pour que le code appelant n'ait qu'à écrire `except LlmError`.
    """


class LlmClient:
    """Envoie des conversations au LLM décrit par LlmSettings. Une seule instance par lancement.

    Utilisation (ce que le reste du code écrira) :
        with LlmClient(load_llm_settings()) as llm:
            text = llm.chat([{"role": "user", "content": "Hello"}])
    """

    def __init__(self, settings: LlmSettings, transport: httpx.BaseTransport | None = None) -> None:
        """
        Entrée :
            settings : base_url, model, api_key (déjà validés : https, ou http vers localhost uniquement),
                reasoning_effort (str ou None), request_timeout (float, en secondes).
            transport : None en usage réel. Dans les tests, un httpx.MockTransport (comme le fait `fake_http`).
        Sortie : rien, mais l'instance est prête à envoyer des requêtes.
        """
        # Ce dont chat() aura besoin à chaque appel.
        self._model = settings.model
        self._reasoning_effort = settings.reasoning_effort

        # Un seul client HTTP pour tout le lancement : il garde la connexion ouverte entre deux appels.
        # La clé API n'existe que dans cet en-tête : jamais dans un attribut ni dans un log.
        self._http_client = httpx.Client(
            base_url=settings.base_url,
            headers={"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {},
            timeout=settings.request_timeout,
            transport=transport,  # None = vrai réseau ; un faux serveur dans les tests.
            follow_redirects=False,  # Never follow: a redirect could send prompts elsewhere.
        )

    def chat(self, messages: list[Message], **options: Any) -> str:
        """Envoie une conversation et renvoie la réponse de l'assistant.

        Entrée :
            messages : la conversation, en général un message "system" + un message "user".
            options : champs optionnels ajoutés au corps de la requête, choisis par l'appelant selon la tâche.
                Exemples : temperature=0, max_tokens=200.
        Sortie :
            Le texte de la réponse (str), jamais vide.
        Lève :
            LlmError pour tout échec.

        TODO, étape par étape :
        1. Construire le corps JSON : model + messages + options,
           + "reasoning_effort" seulement si settings.reasoning_effort n'est pas None.
           Questions : que doit-il se passer si `options` contient aussi "model" ou "messages" ?
           Et si l'appelant passe son propre reasoning_effort dans `options`, qui gagne ?
        2. Envoyer la requête POST.
           Question : quelles exceptions httpx peuvent survenir (connexion, délai dépassé, mauvais code HTTP) ?
           Les transformer en LlmError en gardant la cause d'origine (cherche `raise ... from ...`).
           Pense à `response.raise_for_status()`.
        3. Lire le texte dans choices[0].message.content.
           Le moindre élément manquant (pas de "choices", liste vide, pas de "message", content à None,
           JSON invalide) -> LlmError. Règle de sécurité : on rejette, on ne devine jamais.
        4. Réponse vide ("", "   ") -> LlmError.
        5. Optionnel mais utile : logger.debug() la durée et les tokens consommés.
           Ne jamais logger la clé. Éviter de logger les prompts entiers au niveau INFO (ils contiennent ton profil).
        """
        raise NotImplementedError

    def close(self) -> None:
        """Libère la connexion. TODO : fermer le httpx.Client."""
        raise NotImplementedError

    def __enter__(self) -> "LlmClient":
        """Appelé par `with LlmClient(...) as llm:`. TODO : que doit valoir `llm` ?"""
        raise NotImplementedError

    def __exit__(self, *exc_info: object) -> None:
        """Appelé à la sortie du bloc `with`, même après une exception. TODO : faire le ménage."""
        raise NotImplementedError

