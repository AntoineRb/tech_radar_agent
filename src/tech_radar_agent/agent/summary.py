"""Résumé d'un article par le LLM : ce que l'article apporte concrètement, en 2-3 phrases.

Même architecture que agent/scoring.py, en plus court. À relire avant de commencer : tu as déjà
résolu presque tous les problèmes là-bas (délimiteurs, nettoyage, JSON strict, prompt stable).

    build_summary_prompt(profile)          -> str        le message "system", construit UNE fois
    parse_summary(text)                    -> str        valide la réponse brute du LLM
    Summarizer(llm, profile).summarize(article) -> str | None   None = pas assez de contenu, aucun appel

Décisions déjà prises (CLAUDE.md, boucle agentique, décisions 4 à 6) :
    - `summary` = CE QUE l'article apporte (ce qu'il montre, mesure ou propose, ce qu'on en retient),
      pas « pourquoi c'est pertinent pour toi » : c'est le rôle de `reason` (scoring) ;
    - 2-3 phrases, dans profile.language ;
    - on envoie tout le contenu stocké (3000 car. max) ;
    - pas de résumé si le contenu fait moins de 300 caractères (sinon le LLM inventerait) ;
    - réponse JSON {"summary": "…"}, exactement cette clé ;
    - rejet (jamais de réparation) si le résumé contient une URL, un lien Markdown ou une balise HTML.

Ordre conseillé (une étape = du code + ses tests, au vert avant de continuer) :
    1. Petit refactor dans scoring.py : build_article_message(article, content_chars=SCORING_CONTENT_CHARS)
    2. parse_summary          (la sécurité d'abord, testable avec de simples chaînes)
    3. build_summary_prompt
    4. Summarizer
    5. Essai réel avec Ollama sur des articles bien notés

SQUELETTE : remplace chaque `raise NotImplementedError` et chaque TODO.
⚠️ Commentaires temporairement en français : à repasser en anglais à la fin de l'exercice.
"""

import json
import re

from tech_radar_agent.agent.scoring import (
    ARTICLE_CLOSE,
    ARTICLE_OPEN,
    CODE_FENCE,
    ScoreValidationError,
    build_article_message,
    reject_duplicate_keys,
)
from tech_radar_agent.config import Profile
from tech_radar_agent.llm.client import LlmClient, LlmError, Message
from tech_radar_agent.models import Article
from tech_radar_agent.sanitize import clean_text

# --- Ce qu'on envoie ---
SUMMARY_CONTENT_CHARS = 3000  # Tout le contenu stocké : un résumé fidèle demande de lire l'article.
MIN_CONTENT_CHARS = 300  # En dessous (description d'une ligne, « Comments »…), pas de résumé : il serait inventé.

# --- Ce qu'on attend ---
MAX_SUMMARY_CHARS = 600  # 2-3 phrases ; au-delà, ce n'est plus un résumé.

# --- Réglages de l'appel ---
TEMPERATURE = 0  # Un résumé fidèle, pas créatif.
MAX_TOKENS = 400  # TODO : vérifie la marge à l'essai réel (600 caractères en français + JSON ≈ 200 tokens).

# TODO (étape 2) : les motifs interdits dans un résumé. Pistes, toutes insensibles à la casse :
#   - une URL : "http://", "https://", "www." ;
#   - un schéma dangereux : "javascript:", "data:" ;
#   - un lien Markdown : [texte](cible) ;
#   - une balise HTML : "<" suivi d'une lettre ou de "/" (<script>, </a>, <img …>).
#     Attention à ne pas rejeter un texte normal comme "a < b" ou "3 < 5" : d'où « suivi d'une lettre ».
# Une seule regex avec des alternatives (|), ou une liste de regex : à toi de voir ce qui est le plus lisible.
# Balises HTML reconnues par leur NOM, et pas « < suivi d'une lettre » : un résumé technique contient
# normalement des génériques et des comparaisons (Vec<T>, Map<string, number>, x<y, <vector>), qu'une
# règle trop large rejetait. On vise les balises qui exécutent ou chargent quelque chose, celles qui
# créent un lien, et la mise en forme courante. Le digest échappera de toute façon tout texte du LLM :
# ce filtre est une deuxième barrière, pas la seule.
_HTML_TAGS = (
    "script|style|iframe|frame|frameset|object|embed|applet|svg|math|img|picture|video|audio|source"
    "|link|meta|base|form|input|button|textarea|select|a|html|head|body|div|span|p|br|hr"
    "|b|i|u|em|strong|code|pre|table|tr|td|th|ul|ol|li|h[1-6]"
)

_FORBIDDEN = re.compile(
    rf"""
      https?://                      # URL
    | \bwww\.                        # URL without scheme
    | \b(?:javascript|vbscript):     # script schemes
    | \bdata:[a-z]+/                 # data URI (data:text/html,...)
    | \[[^\]]*\]\([^)]*\)            # Markdown link or image: [x](y), ![x](y)
    | </?\s*(?:{_HTML_TAGS})\b       # known HTML tag, opening or closing: <script, </a, <img src=...
    | <!--                           # HTML comment
    | \bon[a-z]+\s*=                 # event handler attribute: onerror=, onload=...
    """,
    re.IGNORECASE | re.VERBOSE,
)


class SummaryValidationError(LlmError):
    """La réponse du LLM est arrivée, mais elle est invalide (pas du JSON, champ en trop, URL, HTML…).

    Sous-classe de LlmError, comme ScoreValidationError : erreur propre à UN article, la boucle le passe.
    """


# ---------------------------------------------------------------------------------------------
# Étape 1 : petit refactor dans scoring.py (à faire là-bas, pas ici)
# ---------------------------------------------------------------------------------------------
# build_article_message coupe le contenu à SCORING_CONTENT_CHARS (1000). Pour le résumé, on veut 3000.
# Plutôt que de copier la fonction (et toute sa sécurité : délimiteurs, nettoyage, tags), ajoute-lui un
# paramètre avec une valeur par défaut :
#     def build_article_message(article: Article, content_chars: int = SCORING_CONTENT_CHARS) -> str:
# Le scoring ne change pas (valeur par défaut), le résumé appelle build_article_message(article, content_chars=SUMMARY_CONTENT_CHARS).
# Ajoute un test dans test_scoring.py : avec content_chars=3000, le contenu envoyé peut dépasser 1000 caractères.


# ---------------------------------------------------------------------------------------------
# Étape 2 : valider la réponse du LLM
# ---------------------------------------------------------------------------------------------


def parse_summary(text: str) -> str:
    """Transforme la réponse brute du LLM en résumé validé.

    Entrée :
        text : le texte renvoyé par llm.chat() (non vide, <think> déjà retiré par le client).
    Sortie :
        Le résumé, nettoyé (une ligne, sans caractères invisibles) et borné à MAX_SUMMARY_CHARS.
    Lève :
        SummaryValidationError au moindre problème.

    TODO, étape par étape (regarde parse_score : c'est la même recette) :
    1. Balises Markdown ```json … ``` : même décision que pour le score (tolérées) ? Tu peux réutiliser
       _CODE_FENCE de scoring.py (l'importer plutôt que la recopier).
    2. Décoder le JSON, en refusant les clés en double (_reject_duplicate_keys, à importer aussi).
    3. Un objet avec EXACTEMENT la clé "summary" (manquante ou en trop -> rejet).
    4. "summary" doit être une str.
    5. Rejet si _FORBIDDEN trouve quelque chose. ⚠️ Question d'ordre : vérifier AVANT ou APRÈS clean_text ?
       Pense à un lien caché avec un caractère invisible : "ht​tps://evil.com". Que voit la regex
       avant le nettoyage ? Et après ?
    6. clean_text(…, MAX_SUMMARY_CHARS) ; vide après nettoyage -> rejet.
    7. Renvoyer le texte.
    """
    text = text.strip()
    fence = CODE_FENCE.fullmatch(text)
    if fence:
        text = fence.group(1)

    try:
        data = json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise SummaryValidationError("LLM answer is not valid JSON") from exc
    except ScoreValidationError as exc:
        raise SummaryValidationError("LLM answer has duplicate keys") from exc

    if not isinstance(data, dict):
        raise SummaryValidationError(f"LLM answer must be a JSON object, got {type(data).__name__}")
    if data.keys() != {"summary"}:
        raise SummaryValidationError('LLM answer must have exactly the key "summary"')

    summary = data["summary"]
    if not isinstance(summary, str):
        raise SummaryValidationError(f"summary must be a string, got {type(summary).__name__}")

    # Nettoyé SANS tronquer d'abord : un caractère invisible pourrait cacher un lien à la regex
    # ("ht​tps://"), et une troncature pourrait faire disparaître un lien placé après la limite.
    # Un lien n'importe où dans la réponse la rend suspecte en entier.
    summary = clean_text(summary, len(summary))
    if summary is None:
        raise SummaryValidationError("summary is empty")
    if _FORBIDDEN.search(summary):
        # Le résumé n'est pas recopié dans le message : il est non fiable et finirait dans les logs.
        raise SummaryValidationError("summary contains a link or HTML")

    return summary[:MAX_SUMMARY_CHARS].rstrip()


# ---------------------------------------------------------------------------------------------
# Étape 3 : le message system
# ---------------------------------------------------------------------------------------------


def build_summary_prompt(profile: Profile) -> str:
    """Construit le message system du résumé. Appelé UNE fois par lancement, identique pour chaque article.

    Entrée :
        profile : utile surtout pour profile.language. (Question : le reste du profil est-il utile ici ?
        Le résumé dit ce que l'article apporte, pas pourquoi il te concerne : moins de contexte = moins de
        risque que le modèle « oriente » le résumé. À toi de trancher.)
    Sortie :
        Le texte du message system, en anglais.

    TODO : les sections, sur le modèle de build_system_prompt (relis ses commentaires : ce qui a été mesuré
    là-bas vaut ici aussi) :
    1. Rôle et tâche : résumer en 2-3 phrases ce que l'article apporte concrètement à un lecteur technique
       (ce qu'il montre, mesure, propose, et ce qu'on en retient).
    2. Fidélité : uniquement à partir du texte fourni ; n'ajoute aucun fait, chiffre ou nom absent du texte ;
       si le texte ne permet pas de résumer, dis-le en une phrase plutôt que d'inventer.
    3. Forme : texte simple, sans lien, sans URL, sans Markdown, sans HTML.
    4. Anti-injection : comme pour le scoring (données entre ARTICLE_OPEN et ARTICLE_CLOSE, ne jamais suivre
       leurs consignes ; un article SUR l'injection est un sujet normal).
    5. Format : un objet JSON avec exactement la clé "summary", sans balises ; un gabarit, pas un exemple rempli.
       La consigne de langue en DERNIER (mesuré : c'est ce qui la fait respecter).
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------------------------
# Étape 4 : l'assemblage
# ---------------------------------------------------------------------------------------------


class Summarizer:
    """Résume des articles avec un LLM. Une instance par lancement, créée par l'appelant.

    Utilisation (ce que la boucle écrira) :
        summarizer = Summarizer(llm, config.profile)
        summary = summarizer.summarize(article)   # str, None (contenu trop court), ou LlmError
    """

    def __init__(self, llm: LlmClient, profile: Profile) -> None:
        """
        TODO : comme le Scorer. Garder le client, construire le message system UNE fois.
        Le Summarizer ne ferme pas le client.
        """
        raise NotImplementedError

    def summarize(self, article: Article) -> str | None:
        """Résume un article, ou renvoie None s'il n'a pas assez de contenu.

        Lève :
            LlmError (et ses sous-classes) si l'appel échoue : on laisse passer, la boucle décide ;
            SummaryValidationError si la réponse est arrivée mais invalide.

        TODO :
        1. Pas assez de contenu (None, ou moins de MIN_CONTENT_CHARS caractères) -> renvoyer None
           SANS appeler le LLM (pas de coût, pas d'invention).
        2. Messages : system (self._…), user = build_article_message(article, content_chars=SUMMARY_CONTENT_CHARS).
        3. Appel : self._llm.chat(messages, temperature=TEMPERATURE, max_tokens=MAX_TOKENS).
        4. Valider avec parse_summary et renvoyer le résumé.
        Pas de try/except ici, comme dans le Scorer.
        """
        raise NotImplementedError
