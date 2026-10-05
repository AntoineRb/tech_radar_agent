"""La boucle agentique : noter les articles récents, résumer les meilleurs, enregistrer le tout.

    score_and_summarize(conn, scorer, summarizer, settings, model=...)  -> LoopReport

Pour chaque article à noter (fetch_articles_to_score) :
    noter -> save_score -> si score >= seuil : résumer -> save_summary (si le résumé n'est pas None)

Gestion des erreurs (décision 8, voir CLAUDE.md) : la boucle DÉCIDE, le client a déjà CLASSÉ.
- LlmError (de base, dont ScoreValidationError / SummaryValidationError) : propre à un article
  -> passer l'article, continuer. Mais MAX_CONSECUTIVE_FAILURES d'affilée -> arrêt (problème global).
- LlmTemporaryError : réessayer après RETRY_DELAYS (ou retry_after), puis arrêt si ça échoue encore.
- LlmFatalError : arrêt immédiat.
Dans tous les cas, ce qui est déjà enregistré reste en base (save_* commit tout de suite).

⚠️ Commentaires temporairement en français : à repasser en anglais à la fin de l'exercice.
"""

import logging
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from tech_radar_agent.agent.scoring import Scorer
from tech_radar_agent.agent.settings import AgentSettings
from tech_radar_agent.agent.summary import Summarizer
from tech_radar_agent.llm.client import LlmError, LlmFatalError, LlmTemporaryError  # noqa: F401 (à utiliser)
from tech_radar_agent.storage.database import fetch_articles_to_score, save_score, save_summary  # noqa: F401

logger = logging.getLogger(__name__)

T = TypeVar("T")  # Le type renvoyé par l'appel réessayé : Score pour le scoring, str | None pour le résumé.

# --- Garde-fous (décision 8) ---
MAX_CONSECUTIVE_FAILURES = 5  # Échecs « propres à un article » d'affilée -> c'est sans doute global : arrêt.
RETRY_DELAYS = (2.0, 8.0)  # Attentes avant la 2e puis la 3e tentative sur une erreur temporaire.
MAX_RETRY_AFTER = 60.0  # Plafond pour Retry-After. (Question : pourquoi ne pas faire confiance au serveur ?)


# ---------------------------------------------------------------------------------------------
# Étape 1 : ce que la boucle renvoie à main()
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LoopReport:
    """Summary of one run of the scoring loop, for main().

    Each article to score ends up in exactly one of: scored, score_failed, remaining.
    The summary counters only count scored articles, and not all of them: an article below the
    threshold, or whose summary is None (too little content), is in neither. So
    summarized + summary_failed <= scored.

    Attributes:
        total: Number of articles to score when the loop started.
        scored: Articles scored and saved, whatever happened to their summary.
        score_failed: Articles whose scoring failed with an error specific to them. Left unscored,
            retried at the next run.
        summarized: Scored articles whose summary was saved.
        summary_failed: Scored articles whose summary failed with an error specific to them (e.g. an
            invalid answer). Their score is saved without a summary: retrying would give the same
            answer (temperature 0).
        stop_reason: Why the loop stopped early, or None if it ran to the end.
    """

    total: int
    scored: int
    score_failed: int
    summarized: int
    summary_failed: int
    stop_reason: str | None = None

    @property
    def stopped(self) -> bool:
        """Whether the loop stopped before going through every article."""
        return self.stop_reason is not None

    @property
    def remaining(self) -> int:
        """Articles left unscored by an early stop.

        The articles never reached, plus the one the loop stopped on. Whether the stop happened while
        scoring or while summarizing it, nothing is saved for that article: it stays unscored and is
        processed again, from scratch, at the next run.
        """
        return self.total - self.scored - self.score_failed


# ---------------------------------------------------------------------------------------------
# Étape 2 : réessayer un appel sur erreur temporaire
# ---------------------------------------------------------------------------------------------


def call_with_retry(call: Callable[[], T], *, sleep: Callable[[float], None] = time.sleep) -> T:
    """Appelle `call()`, en réessayant sur LlmTemporaryError. Renvoie son résultat.

    Entrées :
        call  : une fonction SANS argument qui fait l'appel au LLM,
                ex. `lambda: scorer.score(article)` (rappel lambda : voir plus bas).
        sleep : la fonction d'attente. time.sleep en vrai ; dans les tests, une fausse fonction qui
                note les durées sans attendre (sinon chaque test durerait 10 s).
    Lève :
        La dernière LlmTemporaryError si toutes les tentatives échouent.
        Toute AUTRE exception (LlmFatalError, LlmError de base…) tout de suite, sans réessayer.

    TODO :
    1. Au plus 1 + len(RETRY_DELAYS) tentatives.
    2. Sur LlmTemporaryError : attendre error.retry_after s'il est donné (plafonné à MAX_RETRY_AFTER),
       sinon le délai de RETRY_DELAYS correspondant ; logger un avertissement (quelle tentative, combien
       de secondes) ; recommencer.
    3. Pas d'attente après la dernière tentative : on relève l'erreur directement.
    Piège : LlmTemporaryError est une sous-classe de LlmError. Ici on n'attrape QUE la temporaire.

    Rappel lambda (exemple hors projet) :
        def twice(f): return f() + f()
        twice(lambda: 21)                 # 42 ; la lambda « emballe » un appel pour le faire plus tard
        twice(lambda: len("abc"))         # 6
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------------------------
# Étape 3 : la boucle
# ---------------------------------------------------------------------------------------------


def score_and_summarize(
    conn: sqlite3.Connection,
    scorer: Scorer,
    summarizer: Summarizer,
    settings: AgentSettings,
    *,
    model: str,
    sleep: Callable[[float], None] = time.sleep,
) -> LoopReport:
    """Note les articles à noter, résume ceux au-dessus du seuil, enregistre tout au fur et à mesure.

    Entrées :
        conn       : la connexion SQLite (créée et fermée par main(), comme aujourd'hui).
        scorer     : un Scorer déjà construit (prompt system calculé une fois).
        summarizer : un Summarizer déjà construit.
        settings   : AgentSettings (fenêtre en jours, max par lancement, seuil de résumé).
        model      : le nom du modèle, stocké dans scored_with (llm_settings.model côté main()).
        sleep      : transmis à call_with_retry (faux dans les tests).
    Sortie :
        Un LoopReport. Ne lève PAS d'exception LLM : un arrêt est une information du bilan, pas un crash.
        (Est-ce le bon choix ? C'est ta réponse à la question de l'étape 1.)

    TODO :
    1. articles = fetch_articles_to_score(conn, settings.max_article_age_days, settings.max_articles_per_run)
       Rien à noter -> bilan vide, sans aucun appel au LLM.
    2. Pour chaque StoredArticle (champs .id et .article) :
       a. score = call_with_retry(lambda: scorer.score(...), sleep=sleep)
       b. Sous le seuil : save_score(conn, stored.id, score=..., reason=..., interests=..., scored_with=model).
       c. À partir du seuil (score.score >= settings.summary_threshold) : résumer (même call_with_retry)
          AVANT d'enregistrer quoi que ce soit, puis selon le résultat (décision A + D, ci-dessous) :
          - résumé (str) : save_score puis save_summary ;
          - None (rien à résumer) : save_score seul ;
          - erreur propre à l'article (SummaryValidationError, LlmError de base) : save_score seul,
            compté dans summary_failed ;
          - arrêt (LlmFatalError, ou LlmTemporaryError après les nouvelles tentatives) : RIEN
            d'enregistré pour cet article, arrêt de la boucle.
       d. compteurs du bilan (voir la docstring de LoopReport).
    3. Les trois catégories d'erreurs (voir la docstring du module). Où placer le try/except : autour de
       tout le traitement d'un article, ou séparément autour du scoring et du résumé ? Indice : une
       erreur d'article ne mène pas au même enregistrement selon qu'elle arrive à la note ou au résumé.
    4. Le compteur d'échecs consécutifs : quand le remettre à zéro ? Un échec de résumé compte-t-il ?
    5. Logs : un message par article raté (titre + type d'erreur), un par arrêt (pourquoi). Jamais la
       réponse brute du LLM dans les logs (non fiable). Le bilan final, c'est main() qui l'écrit.

    Décision A + D (résumé en échec après une note réussie), selon que réessayer peut aider ou non :
    - Réponse invalide : la note est enregistrée sans résumé (A). Réessayer ne servirait à rien
      (temperature=0 : même entrée, même réponse) ; l'article reste utile dans le digest.
    - Arrêt pendant le résumé (serveur en panne) : rien n'est enregistré (D). L'article reste non noté,
      fetch_articles_to_score le reprend en entier au lancement suivant. Coût : une notation refaite.
    Écarté : C (requête de rattrapage des résumés manquants) : colonne ou sentinelle en plus pour
    distinguer « rien à résumer » d'« échec », pour des données non critiques. Possible plus tard si
    des résumés manquent dans les vrais digests.
    """
    raise NotImplementedError
