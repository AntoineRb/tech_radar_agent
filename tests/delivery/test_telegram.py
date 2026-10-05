"""Tests for delivery/telegram.py, against a fake Telegram server (httpx.MockTransport). No network.

The most important group checks that the bot token never leaks: not in an error message, not in a
full traceback (exception chaining included), not in the logs, whatever goes wrong.
"""

import json
import logging
import traceback

import httpx
import pytest

from tech_radar_agent.agent.render import MAX_MESSAGE_LENGTH, Block
from tech_radar_agent.delivery.telegram import (
    MAX_RETRY_AFTER,
    RETRY_DELAYS,
    DeliveryReport,
    OutgoingMessage,
    TelegramClient,
    TelegramError,
    TelegramFatalError,
    TelegramSettings,
    TelegramTemporaryError,
    load_telegram_settings,
    pack_messages,
    send_digest,
)

TOKEN = "123456789:AAH-secret_token_value_for_tests_only_xyz"
CHAT_ID = 1320919177
SETTINGS = TelegramSettings(bot_token=TOKEN, chat_id=CHAT_ID)


# --- Settings ---


def test_settings_are_read_from_the_environment():
    settings = load_telegram_settings({"TELEGRAM_BOT_TOKEN": f"  {TOKEN} ", "TELEGRAM_CHAT_ID": f" {CHAT_ID} "})
    assert settings == SETTINGS


def test_token_is_hidden_from_repr():
    assert TOKEN not in repr(SETTINGS)


@pytest.mark.parametrize(
    ("environ", "message"),
    [
        ({}, "TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID"),
        ({"TELEGRAM_CHAT_ID": "1"}, "Missing environment variables: TELEGRAM_BOT_TOKEN"),
        ({"TELEGRAM_BOT_TOKEN": TOKEN}, "Missing environment variables: TELEGRAM_CHAT_ID"),
        ({"TELEGRAM_BOT_TOKEN": "not-a-token", "TELEGRAM_CHAT_ID": "1"}, "does not look like a bot token"),
        ({"TELEGRAM_BOT_TOKEN": "123:short", "TELEGRAM_CHAT_ID": "1"}, "does not look like a bot token"),
        ({"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": "@antoine"}, "whole number"),
        ({"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": "-1001234567890"}, "not a group or a channel"),
        ({"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": "0"}, "not a group or a channel"),
    ],
    ids=["nothing", "no-token", "no-chat", "bad-token", "short-token", "username", "group", "zero"],
)
def test_invalid_settings(environ, message):
    with pytest.raises(ValueError, match=message) as raised:
        load_telegram_settings(environ)
    assert TOKEN not in str(raised.value)


# --- Packing blocks into messages ---


def test_small_digest_is_one_message_with_all_its_article_ids():
    blocks = [Block("header"), Block("<b>title</b>"), Block("entry 1", 11), Block("entry 2", 22)]
    assert pack_messages(blocks) == [OutgoingMessage("header\n\n<b>title</b>\n\nentry 1\n\nentry 2", (11, 22))]


def test_blocks_are_never_cut_and_ids_follow_their_message():
    entry = "e" * 1500  # Two fit in a message (3002 with the separator), a third does not (4504).
    blocks = [Block(entry, 1), Block(entry, 2), Block(entry, 3), Block(entry, 4), Block(entry, 5)]
    messages = pack_messages(blocks)
    assert [message.article_ids for message in messages] == [(1, 2), (3, 4), (5,)]
    assert all(len(message.text) <= MAX_MESSAGE_LENGTH for message in messages)
    assert all(text == entry for message in messages for text in message.text.split("\n\n"))


def test_a_message_can_be_exactly_the_limit():
    half = (MAX_MESSAGE_LENGTH - 2) // 2
    messages = pack_messages([Block("a" * half, 1), Block("b" * half, 2)])
    assert len(messages) == 1 and len(messages[0].text) == MAX_MESSAGE_LENGTH


def test_packing_counts_emojis_as_telegram_does():
    # 2000 emojis = 4000 UTF-16 units: with the separator, a second one-emoji block exceeds the limit.
    blocks = [Block("🟢" * 2000, 1), Block("🟢" * 50, 2)]
    assert len(pack_messages(blocks)) == 2


def test_no_block_gives_no_message():
    assert pack_messages([]) == []


# --- The client, against a fake Telegram server ---


class FakeTelegram:
    """Answers sendMessage with the replies given, in order (the last one repeats). Records requests."""

    def __init__(self, *replies) -> None:
        self.replies = list(replies) or [httpx.Response(200, json={"ok": True, "result": {}})]
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply

    def client(self) -> TelegramClient:
        return TelegramClient(SETTINGS, transport=httpx.MockTransport(self.handle))


def refused(code: int, description: str = "Bad Request", **parameters) -> httpx.Response:
    body = {"ok": False, "error_code": code, "description": description}
    if parameters:
        body["parameters"] = parameters
    return httpx.Response(code, json=body)


OK = httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})


def test_send_posts_html_to_the_chat_without_link_preview():
    server = FakeTelegram(OK)
    with server.client() as client:
        client.send("<b>Hello</b>")
    [request] = server.requests
    assert request.method == "POST"
    assert str(request.url) == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert json.loads(request.content) == {
        "chat_id": CHAT_ID,
        "text": "<b>Hello</b>",
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }


@pytest.mark.parametrize(
    ("reply", "error_type"),
    [
        (refused(400, "Bad Request: can't parse entities"), TelegramError),
        (refused(429, "Too Many Requests: retry after 5", retry_after=5), TelegramTemporaryError),
        (refused(500, "Internal Server Error"), TelegramTemporaryError),
        (httpx.Response(502, text="<html>Bad Gateway</html>"), TelegramTemporaryError),
        (refused(401, "Unauthorized"), TelegramFatalError),
        (refused(403, "Forbidden: bot was blocked by the user"), TelegramFatalError),
        (refused(404, "Not Found"), TelegramFatalError),
        (httpx.Response(302, headers={"Location": "https://elsewhere.example"}), TelegramFatalError),
        (httpx.ConnectTimeout("timed out"), TelegramTemporaryError),
        (httpx.ConnectError("connection refused"), TelegramTemporaryError),
        (httpx.ReadError("connection reset"), TelegramTemporaryError),
    ],
    ids=["400", "429", "500", "502-not-json", "401", "403-blocked", "404", "redirect", "timeout", "connect", "read"],
)
def test_errors_are_classified(reply, error_type):
    with pytest.raises(TelegramError) as raised, FakeTelegram(reply).client() as client:
        client.send("text")
    assert type(raised.value) is error_type


def test_retry_after_is_read_from_telegram():
    with pytest.raises(TelegramTemporaryError) as raised, FakeTelegram(refused(429, retry_after=7)).client() as client:
        client.send("text")
    assert raised.value.retry_after == 7


def test_telegram_description_is_kept_in_the_error():
    with pytest.raises(TelegramError, match="can't parse entities"), FakeTelegram(
        refused(400, "Bad Request: can't parse entities")
    ).client() as client:
        client.send("text")


# --- The token never leaks ---


@pytest.mark.parametrize(
    "reply",
    [
        httpx.ConnectError(f"Failed to connect to https://api.telegram.org/bot{TOKEN}/sendMessage"),
        httpx.ReadTimeout(f"Read timed out for https://api.telegram.org/bot{TOKEN}/sendMessage"),
        refused(400, f"Bad Request: echoing the URL https://api.telegram.org/bot{TOKEN}/sendMessage"),
        refused(500, f"error near bot{TOKEN}"),
        httpx.Response(302, headers={"Location": f"https://evil.example/bot{TOKEN}"}),
    ],
    ids=["connect-error-with-url", "timeout-with-url", "400-echoing-url", "500-echoing-token", "redirect"],
)
def test_the_token_never_appears_in_errors_or_tracebacks(reply):
    with pytest.raises(TelegramError) as raised, FakeTelegram(reply).client() as client:
        client.send("text")
    error = raised.value
    assert TOKEN not in str(error) and TOKEN not in repr(error)
    # Never chained to an httpx error (which holds the URL): no cause, and any context is suppressed.
    assert error.__cause__ is None and (error.__context__ is None or error.__suppress_context__)
    assert TOKEN not in "".join(traceback.format_exception(error))


def test_the_token_never_appears_in_logs(caplog):
    server = FakeTelegram(
        httpx.ConnectError(f"Failed to connect to https://api.telegram.org/bot{TOKEN}/sendMessage"),
        refused(400, f"bot{TOKEN}"),
        refused(429, retry_after=1),
        refused(401, f"bot{TOKEN} unauthorized"),
    )
    with caplog.at_level("DEBUG"), server.client() as client:
        messages = [OutgoingMessage("a", (1,)), OutgoingMessage("b", (2,))]
        send_digest(client, messages, lambda ids: None, sleep=lambda seconds: None)
    assert caplog.text  # Something was logged...
    assert TOKEN not in caplog.text  # ...never the token, even from httpx itself.


# --- Sending a digest ---


class Marked:
    """Records the article ids passed to on_sent, like main() will mark them as sent."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, ...]] = []

    def __call__(self, ids: tuple[int, ...]) -> None:
        self.calls.append(ids)


MESSAGES = [OutgoingMessage("one", (1, 2)), OutgoingMessage("two", (3,)), OutgoingMessage("three", (4, 5))]


def run(*replies, messages=MESSAGES):
    server, marked, waits = FakeTelegram(*replies), Marked(), []
    with server.client() as client:
        report = send_digest(client, messages, marked, sleep=waits.append)
    return report, marked.calls, waits, server


def test_all_messages_sent_and_marked_one_by_one():
    report, marked, waits, server = run(OK)
    assert report == DeliveryReport(total=3, sent=3, failed=0) and report.complete
    assert marked == [(1, 2), (3,), (4, 5)]  # Each message marked once Telegram confirmed it.
    assert waits == [] and len(server.requests) == 3


def test_a_message_without_articles_is_sent_but_marks_nothing():
    report, marked, _, _ = run(OK, messages=[OutgoingMessage("header only", ())])
    assert report.sent == 1 and marked == []


def test_temporary_errors_are_retried():
    report, marked, waits, server = run(refused(503), refused(429, retry_after=3), OK, OK, OK)
    assert report.complete and marked == [(1, 2), (3,), (4, 5)]
    assert waits == [RETRY_DELAYS[0], 3]  # Telegram's retry_after replaces the default delay.


def test_retry_after_is_capped():
    _, _, waits, _ = run(refused(429, retry_after=86400), OK)
    assert waits == [MAX_RETRY_AFTER]


def test_temporary_error_that_lasts_stops_sending_and_keeps_what_was_sent():
    report, marked, waits, _ = run(OK, refused(503))
    assert marked == [(1, 2)]  # Message 1 confirmed: marked. Messages 2 and 3: unsent, back tomorrow.
    assert (report.sent, report.failed, report.total) == (1, 0, 3)
    assert "TelegramTemporaryError" in report.stop_reason and not report.complete
    assert waits == list(RETRY_DELAYS)


def test_fatal_error_stops_at_once():
    report, marked, waits, server = run(OK, refused(403, "Forbidden: bot was blocked by the user"))
    assert marked == [(1, 2)]
    assert "blocked" in report.stop_reason
    assert waits == [] and len(server.requests) == 2  # Message 3 never tried.


def test_a_refused_message_is_skipped_and_the_others_go_on():
    report, marked, _, _ = run(OK, refused(400, "Bad Request: can't parse entities"), OK)
    assert marked == [(1, 2), (4, 5)]  # Message 2's articles stay unsent.
    assert (report.sent, report.failed, report.stop_reason) == (2, 1, None)
    assert not report.complete


def test_nothing_is_marked_before_telegram_confirms():
    # The first answer fails: on_sent must not have been called for it.
    _, marked, _, _ = run(refused(401), messages=[OutgoingMessage("one", (1,))])
    assert marked == []


def test_httpx_request_logs_are_redacted_while_the_client_is_open(caplog):
    # httpx itself logs every request URL at INFO: the token must be replaced, at any log level.
    with caplog.at_level("DEBUG"), FakeTelegram(OK).client() as client:
        client.send("text")
    assert "HTTP Request: POST https://api.telegram.org/bot<token>/sendMessage" in caplog.text
    assert TOKEN not in caplog.text


def test_closing_the_client_removes_its_log_filter():
    before = list(logging.getLogger("httpx").filters)
    with FakeTelegram(OK).client():
        assert len(logging.getLogger("httpx").filters) == len(before) + 1
    assert logging.getLogger("httpx").filters == before
