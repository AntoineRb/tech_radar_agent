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
import re
import time
from typing import Any

import httpx

from tech_radar_agent.llm.settings import LlmSettings
from tech_radar_agent.sanitize import clean_text

logger = logging.getLogger(__name__)

# Un message de la conversation : {"role": "system" | "user" | "assistant", "content": "..."}.
Message = dict[str, str]

# Le délai d'attente et reasoning_effort ne sont PAS des constantes ici : ils viennent de LlmSettings
# (variables LLM_REQUEST_TIMEOUT et LLM_REASONING_EFFORT, voir .env.example), pour s'adapter à l'environnement.
#   settings.request_timeout : float, 30 par défaut
#   settings.reasoning_effort : str ou None (None = ne pas envoyer le champ)

# Champs du corps gérés par le client : un appelant ne peut pas les remplacer via `options`.
_RESERVED_KEYS = frozenset({"model", "messages"})

# Bloc de réflexion qu'écrivent certains modèles dans leur réponse (compilé une seule fois).
_THINK_BLOCK = re.compile(r"<think>.*?</think>", flags=re.DOTALL)


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
            LlmError pour tout échec du LLM.
            TypeError si l'appelant passe une option réservée (bug dans le code appelant).
        """
        # Construit le corps avant le `try` : une option interdite est un bug de l'appelant,
        # pas une panne du LLM, elle ne doit donc pas devenir une LlmError.
        body = self._build_body(messages, options)

        # --- 1. Envoi de la requête : toutes les erreurs réseau et HTTP deviennent des LlmError ---
        # perf_counter() : horloge précise faite pour mesurer des durées (pas l'heure du jour).
        # On n'utilise pas response.elapsed : il n'est pas toujours disponible selon le transport.
        started = time.perf_counter()
        try:
            # base_url est déjà dans le client : on ne donne que la fin du chemin.
            # `json=` encode le dict en JSON et ajoute l'en-tête Content-Type tout seul.
            response = self._http_client.post("/chat/completions", json=body)
            # Lève HTTPStatusError pour tout code hors 2xx : 401 (mauvaise clé), 429 (trop de requêtes),
            # 500 (serveur en panne), et aussi 3xx (redirection, puisqu'on ne les suit pas).
            response.raise_for_status()
        # L'ordre compte : TimeoutException est un cas particulier de RequestError,
        # elle doit donc être testée avant, sinon le bloc RequestError l'attraperait.
        except httpx.TimeoutException as exc:
            # `from exc` garde l'erreur d'origine dans __cause__ : elle apparaît dans la trace pour déboguer.
            raise LlmError(f"LLM request timed out ({type(exc).__name__})") from exc
        except httpx.HTTPStatusError as exc:
            # Le début du corps contient souvent l'explication du serveur (ex. « reasoning_effort non supporté »).
            # Ce texte vient d'un serveur extérieur et finira dans les logs : nettoyé et tronqué.
            detail = clean_text(exc.response.text, 200) or "no details"
            raise LlmError(f"LLM server returned HTTP {exc.response.status_code}: {detail}") from exc
        except httpx.RequestError as exc:
            # Toutes les autres erreurs de transport : serveur éteint, DNS inconnu, connexion coupée…
            raise LlmError(f"Could not reach LLM server ({type(exc).__name__})") from exc

        # --- 2. Décodage du JSON ---
        try:
            data = response.json()
        except ValueError as exc:  # JSONDecodeError est une sous-classe de ValueError.
            raise LlmError("LLM response is not valid JSON") from exc

        # --- 3. Extraction du texte : choices[0].message.content ---
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
            # Pourquoi le modèle s'est arrêté : "stop" (fin normale), "length" (max_tokens atteint)…
            finish_reason = choice.get("finish_reason")
        # KeyError : une clé manque ; IndexError : "choices" est une liste vide ;
        # TypeError / AttributeError : un élément n'a pas le bon type (ex. data est une liste, choice une chaîne).
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise LlmError("LLM response has an unexpected structure") from exc

        # Réponse coupée par max_tokens : un résumé tronqué ou un JSON incomplet n'est pas une réponse.
        if finish_reason == "length":
            raise LlmError("LLM response was cut off (max_tokens reached)")

        # content peut valoir None (certains serveurs, quand la génération est coupée) : on refuse.
        if not isinstance(content, str):
            raise LlmError(f"LLM response content is not text (got {type(content).__name__})")

        # Certains modèles écrivent leur réflexion dans la réponse, entre <think> et </think> : on la retire.
        # DOTALL : le « . » accepte aussi les retours à la ligne ; « .*? » s'arrête au premier </think>.
        content = _THINK_BLOCK.sub("", content).strip()

        # Un <think> restant veut dire que la réflexion n'a jamais été fermée : ce n'est pas une réponse.
        if "<think>" in content:
            raise LlmError("LLM response contains an unfinished <think> block")

        # Règle de sécurité : une réponse vide est rejetée, jamais devinée.
        if not content:
            raise LlmError("LLM returned an empty response")

        # --- 4. Log de suivi : durée et tokens, jamais la clé ni le contenu des prompts ---
        usage = data.get("usage") or {}  # "usage" est facultatif selon le serveur.
        logger.debug(
            "LLM call: model=%s duration=%.2fs prompt_tokens=%s completion_tokens=%s",
            self._model,
            time.perf_counter() - started,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )
        return content

    def _build_body(self, messages: list[Message], options: dict[str, Any]) -> dict[str, Any]:
        """Assemble le corps JSON de la requête : model + messages + reasoning_effort + options."""
        # `&` entre deux ensembles donne leur intersection : les clés réservées présentes dans options.
        conflicts = _RESERVED_KEYS & options.keys()
        if conflicts:
            raise TypeError(f"Reserved options, managed by the client: {sorted(conflicts)}")

        body: dict[str, Any] = {
            "model": self._model,
            # Copie de chaque message : le client ne modifie jamais la liste de l'appelant.
            "messages": [dict(message) for message in messages],
        }
        # Envoyé seulement s'il est défini dans l'environnement (LLM_REASONING_EFFORT).
        if self._reasoning_effort:
            body["reasoning_effort"] = self._reasoning_effort

        # Ajouté en dernier : une option de l'appelant remplace la valeur par défaut des settings
        # (ex. reasoning_effort="low" pour une tâche qui a besoin de réfléchir).
        body.update(options)

        # None veut dire « n'envoie pas ce champ » : jamais de null envoyé au serveur (il pourrait le refuser).
        # Ex. chat(..., reasoning_effort=None) retire le reasoning_effort des settings pour cet appel.
        return {key: value for key, value in body.items() if value is not None}

    def close(self) -> None:
        """Libère la connexion. TODO : fermer le httpx.Client."""
        raise NotImplementedError

    def __enter__(self) -> "LlmClient":
        """Appelé par `with LlmClient(...) as llm:`. TODO : que doit valoir `llm` ?"""
        raise NotImplementedError

    def __exit__(self, *exc_info: object) -> None:
        """Appelé à la sortie du bloc `with`, même après une exception. TODO : faire le ménage."""
        raise NotImplementedError

