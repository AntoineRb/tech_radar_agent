"""Tests à écrire pour agent/summary.py. Chacun est ignoré (skip) tant que tu ne l'as pas écrit : retire `@TODO`.

Même méthode que test_scoring.py, que tu peux réutiliser :
- `answer(...)`-style : une petite fonction qui fabrique une réponse valide, '{"summary": "…"}', dont chaque test change une chose ;
- make_article / make_profile : importe-les depuis test_scoring.py ou recopie-les (ce sont des fonctions de test) ;
- FakeLlm : idem, un faux client qui enregistre les appels et renvoie la réponse choisie.

Lancer un groupe : uv run pytest tests/agent/test_summary.py -k parse_summary

⚠️ Commentaires temporairement en français : à repasser en anglais à la fin de l'exercice.
"""

import pytest

TODO = pytest.mark.skip(reason="TODO: to write with the agent/summary.py implementation")


# --- Étape 1 : build_article_message(article, content_chars=…) : ✅ testé dans test_scoring.py ---


# --- Étape 2 : parse_summary ---


@TODO
def test_parse_summary_valid_answer():
    """'{"summary": "Les auteurs mesurent…"}' -> "Les auteurs mesurent…"."""


@TODO
def test_parse_summary_is_cleaned_and_truncated():
    """Caractères invisibles retirés, une seule ligne, longueur <= MAX_SUMMARY_CHARS."""


@TODO
def test_parse_summary_rejects_invalid_json_or_shape():
    """Paramétrer : texte libre, JSON tronqué, liste JSON, objet sans "summary", clé en trop, clé en double."""


@TODO
def test_parse_summary_rejects_non_text_or_empty():
    """"summary": null, 42, ["a"], "", "   ", "\\u200b" -> SummaryValidationError."""


@TODO
def test_parse_summary_rejects_urls():
    """Paramétrer : https://evil.com, http://…, www.evil.com, HTTPS://EVIL.COM (casse), javascript:alert(1), data:text/html,…"""


@TODO
def test_parse_summary_rejects_markdown_links():
    """"Lire [ici](https://evil.com)" et "[ici](evil)" -> rejet."""


@TODO
def test_parse_summary_rejects_html():
    """<script>…</script>, <img src=x onerror=alert(1)>, </a>, <b>gras</b>, <IMG …> -> rejet."""


@TODO
def test_parse_summary_accepts_normal_comparisons():
    """"Latence < 5 ms", "a < b", "2 > 1", "l'API .NET", "e-mail" ne doivent PAS être rejetés (pas de faux positifs)."""


@TODO
def test_parse_summary_rejects_hidden_links():
    """Un lien masqué par un caractère invisible ("ht\\u200btps://evil.com", "www\\u200b.evil.com") -> rejet."""


@TODO
def test_parse_summary_tolerates_markdown_fences():
    """Selon ta décision : ```json {"summary": "…"} ``` accepté, texte autour rejeté."""


@TODO
def test_summary_validation_error_is_an_llm_error():
    """issubclass(SummaryValidationError, LlmError)."""


# --- Étape 3 : build_summary_prompt ---


@TODO
def test_summary_prompt_asks_for_the_profile_language_last():
    """"French" dans la consigne de langue, et cette consigne est la dernière ligne (même garde-fou que le scoring)."""


@TODO
def test_summary_prompt_forbids_invented_facts_links_and_html():
    """Les consignes de fidélité (« only from the provided text ») et de forme (pas de lien, pas de HTML) sont présentes."""


@TODO
def test_summary_prompt_mentions_the_delimiters():
    """ARTICLE_OPEN, ARTICLE_CLOSE et la consigne de ne jamais suivre les instructions de l'article."""


@TODO
def test_summary_prompt_is_stable():
    """Même profil -> même texte (cache de préfixe)."""


@TODO
def test_summary_prompt_has_no_filled_example():
    """Un gabarit, pas un exemple rempli que le modèle recopierait."""


# --- Étape 4 : Summarizer ---


@TODO
def test_summarizer_skips_articles_without_enough_content():
    """content=None, "Comments", 299 caractères -> None, et le faux client n'a reçu AUCUN appel."""


@TODO
def test_summarizer_summarizes_articles_with_enough_content():
    """300 caractères ou plus -> le résumé validé est renvoyé."""


@TODO
def test_summarizer_sends_system_then_user_message_with_the_full_content():
    """2 messages ; le message user contient le contenu jusqu'à SUMMARY_CONTENT_CHARS (plus que les 1000 du scoring)."""


@TODO
def test_summarizer_uses_the_call_settings():
    """temperature=TEMPERATURE, max_tokens=MAX_TOKENS, et ni tools ni response_format."""


@TODO
def test_summarizer_builds_the_prompt_once():
    """3 articles résumés -> build_summary_prompt appelé une seule fois."""


@TODO
def test_summarizer_lets_errors_through():
    """LlmError, LlmTemporaryError, LlmFatalError et SummaryValidationError remontent telles quelles."""


@TODO
def test_injection_in_article_stays_in_the_user_message():
    """Le texte d'une injection n'apparaît jamais dans le message system."""
