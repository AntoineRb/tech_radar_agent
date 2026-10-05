"""Tests à écrire pour agent/loop.py. Chacun est ignoré (skip) tant que tu ne l'as pas écrit : retire `@TODO`.

Méthode (aucun LLM, aucun vrai sleep) :
- une vraie base dans tmp_path : connect(tmp_path / "test.db") + save_articles(...) pour la remplir ;
- de faux Scorer / Summarizer : de petites classes avec score(article) / summarize(article), qui
  renvoient ou lèvent ce que le test choisit (une liste de réponses consommée dans l'ordre, par exemple) ;
- un faux sleep : `waits = []` puis `sleep=waits.append` (note les durées, n'attend pas).
Relire ensuite la base avec un SELECT pour vérifier score / reason / summary.

Lancer un groupe : uv run pytest tests/agent/test_loop.py -k retry

⚠️ Commentaires temporairement en français : à repasser en anglais à la fin de l'exercice.
"""

import pytest

TODO = pytest.mark.skip(reason="TODO: to write with the agent/loop.py implementation")


# --- Étape 2 : call_with_retry ---


@TODO
def test_retry_returns_result_without_waiting():
    """Succès du premier coup -> résultat renvoyé, aucun appel à sleep."""


@TODO
def test_retry_succeeds_after_temporary_errors():
    """2 LlmTemporaryError puis succès -> résultat ; attentes == list(RETRY_DELAYS)."""


@TODO
def test_retry_gives_up_after_all_attempts():
    """Toujours LlmTemporaryError -> relevée après 1 + len(RETRY_DELAYS) appels ; pas d'attente après le dernier."""


@TODO
def test_retry_uses_retry_after_when_given():
    """LlmTemporaryError(retry_after=5) -> attente de 5 s, pas du délai par défaut."""


@TODO
def test_retry_after_is_capped():
    """retry_after=86400 (serveur hostile ou bogué) -> attente plafonnée à MAX_RETRY_AFTER."""


@TODO
def test_retry_does_not_retry_other_errors():
    """Paramétrer : LlmFatalError, LlmError de base, ScoreValidationError -> relevée tout de suite, 1 seul appel."""


# --- Étape 3 : score_and_summarize, cas nominaux ---


@TODO
def test_nothing_to_score_makes_no_llm_call():
    """Base vide (ou seulement de vieux articles) -> bilan vide, faux Scorer jamais appelé."""


@TODO
def test_scores_are_saved():
    """Score enregistré : score, reason, interests (JSON), scored_with == model, scored_at rempli."""


@TODO
def test_summary_only_at_or_above_threshold():
    """Seuil 8 : notes 7, 8, 9 -> Summarizer appelé pour 8 et 9 seulement (cas limite : 8 == seuil)."""


@TODO
def test_none_summary_is_not_saved():
    """Summarizer renvoie None (contenu trop court) -> summary reste NULL, l'article compte comme noté."""


@TODO
def test_report_counts():
    """Mélange de notes, résumés, échecs -> chaque compteur du LoopReport est juste."""


# --- Étape 3 : erreurs ---


@TODO
def test_article_error_skips_article_and_continues():
    """ScoreValidationError sur le 2e article -> 1er et 3e notés, 2e reste à score NULL (retenté plus tard)."""


@TODO
def test_consecutive_article_errors_stop_the_loop():
    """MAX_CONSECUTIVE_FAILURES erreurs d'affilée -> arrêt ; les articles suivants ne sont pas appelés."""


@TODO
def test_success_resets_consecutive_errors():
    """4 erreurs, 1 succès, 4 erreurs -> pas d'arrêt."""


@TODO
def test_fatal_error_stops_immediately():
    """LlmFatalError au 2e article -> arrêt, 1er article bien enregistré, 3e jamais appelé."""


@TODO
def test_temporary_error_exhausted_stops_the_loop():
    """LlmTemporaryError à chaque tentative -> arrêt après les nouvelles tentatives ; le déjà-noté est conservé."""


@TODO
def test_summary_error_keeps_the_score():
    """Note 9, puis SummaryValidationError (A) -> note enregistrée, summary NULL, summary_failed == 1, la boucle continue."""


@TODO
def test_fatal_error_during_summary_stops_the_loop():
    """LlmFatalError pendant le RÉSUMÉ (D) -> arrêt ; cet article reste à score NULL (rien enregistré), compté dans remaining.

    Variante à paramétrer : LlmTemporaryError à chaque tentative pendant le résumé -> même résultat.
    """


@TODO
def test_unexpected_exception_is_not_swallowed():
    """Un bug (ex. RuntimeError dans le faux Scorer) n'est PAS avalé par la boucle : il remonte."""
