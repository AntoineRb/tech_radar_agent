"""Sending the digest on Telegram, through the official Bot API (ADR 0026).

    load_telegram_settings(environ)                     -> TelegramSettings   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    pack_messages(blocks)                               -> list[OutgoingMessage]   whole blocks per message
    TelegramClient(settings).send(text)                                       one message, errors classified
    send_digest(client, messages, on_sent, sleep=...)   -> DeliveryReport

The secret: the bot token is part of every API URL (https://api.telegram.org/bot<TOKEN>/sendMessage),
and httpx puts the URL in its error messages. So no httpx error is ever passed on: each one is rebuilt
from its type only, with `raise ... from None` so it is not chained into a traceback either. GitHub
masks secrets in Actions logs, but only their exact value; this does not rely on it. httpx also logs
every request URL itself (logger "httpx", INFO): while a client is open, a filter on that logger
replaces the token with <token>, whatever level the logs are set to.

This module never touches the database: send_digest calls `on_sent(article_ids)` after each message
Telegram confirmed, and the caller marks those articles as sent. Nothing is ever marked before.
"""

import logging
import os
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import httpx

from tech_radar_agent.agent.render import MAX_MESSAGE_LENGTH, Block, telegram_length
from tech_radar_agent.sanitize import clean_text

logger = logging.getLogger(__name__)

API_URL = "https://api.telegram.org"
REQUEST_TIMEOUT = 15.0  # Seconds for one call; Telegram usually answers in well under a second.
TOKEN_FORMAT = re.compile(r"\d+:[A-Za-z0-9_-]{30,}")  # As given by @BotFather: "<bot id>:<secret>".
RETRY_DELAYS = (2.0, 8.0)  # Waits before the 2nd and 3rd attempt after a temporary error.
MAX_RETRY_AFTER = 60.0  # Cap on Telegram's retry_after: a buggy answer must not block the run.
BLOCK_SEPARATOR = "\n\n"


# --- Settings ---


@dataclass(frozen=True)
class TelegramSettings:
    """Where to send the digest. Deployment settings, so they live in the environment (ADR 0011)."""

    bot_token: str = field(repr=False)  # repr=False: never printed in logs.
    chat_id: int  # A private chat: positive. Groups and channels (negative ids) are refused.


def load_telegram_settings(environ: Mapping[str, str] = os.environ) -> TelegramSettings:
    """Read TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID. Errors name the variable, never the token."""
    token = environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    raw_chat_id = environ.get("TELEGRAM_CHAT_ID", "").strip()

    missing = [name for name, value in (("TELEGRAM_BOT_TOKEN", token), ("TELEGRAM_CHAT_ID", raw_chat_id)) if not value]
    if missing:
        raise ValueError(f"Missing environment variables: {', '.join(missing)} (see .env.example)")
    if not TOKEN_FORMAT.fullmatch(token):
        raise ValueError("TELEGRAM_BOT_TOKEN does not look like a bot token from @BotFather ('<digits>:<secret>')")
    try:
        chat_id = int(raw_chat_id)
    except ValueError:
        raise ValueError("TELEGRAM_CHAT_ID must be a whole number (your private chat id)") from None
    if chat_id <= 0:
        # Negative ids are groups and channels: the digest is personal, it must never go to a group.
        raise ValueError("TELEGRAM_CHAT_ID must be a private chat id (a positive number), not a group or a channel")
    return TelegramSettings(bot_token=token, chat_id=chat_id)


# --- Messages ---


@dataclass(frozen=True)
class OutgoingMessage:
    """One Telegram message: whole digest blocks, and the articles it carries."""

    text: str
    article_ids: tuple[int, ...]


def pack_messages(blocks: Sequence[Block]) -> list[OutgoingMessage]:
    """Group whole blocks into as few messages as possible, each within MAX_MESSAGE_LENGTH.

    A block is never cut: a cut inside a tag or an entity makes Telegram reject the whole message.
    render_digest already left out any entry too long for a message on its own.
    """
    messages: list[OutgoingMessage] = []
    texts: list[str] = []
    ids: list[int] = []
    for block in blocks:
        candidate = BLOCK_SEPARATOR.join([*texts, block.html])
        if texts and telegram_length(candidate) > MAX_MESSAGE_LENGTH:
            messages.append(OutgoingMessage(BLOCK_SEPARATOR.join(texts), tuple(ids)))
            texts, ids = [], []
        texts.append(block.html)
        if block.article_id is not None:
            ids.append(block.article_id)
    if texts:
        messages.append(OutgoingMessage(BLOCK_SEPARATOR.join(texts), tuple(ids)))
    return messages


# --- Client ---


class TelegramError(Exception):
    """Telegram refused this message (e.g. 400: invalid HTML). Other messages may still go through."""


class TelegramTemporaryError(TelegramError):
    """Rate limited, server busy, timeout, network glitch: retrying later may work."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after  # Seconds Telegram asked to wait, if it said so.


class TelegramFatalError(TelegramError):
    """Bad token, bot blocked by the reader, unknown chat, wrong address: every message would fail."""


class _RedactToken(logging.Filter):
    """Replaces the token in any log record of the logger it is attached to."""

    def __init__(self, token: str) -> None:
        super().__init__()
        self._token = token

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if self._token in message:
            record.msg, record.args = message.replace(self._token, "<token>"), ()
        return True  # Never drops a record, only rewrites it.


class TelegramClient:
    """Sends messages to one chat. One instance per run; use it in a `with` block."""

    def __init__(self, settings: TelegramSettings, transport: httpx.BaseTransport | None = None) -> None:
        self._token = settings.bot_token
        self._chat_id = settings.chat_id
        # httpx logs "HTTP Request: POST https://api.telegram.org/bot<TOKEN>/..." at INFO: redact it.
        self._redact = _RedactToken(self._token)
        logging.getLogger("httpx").addFilter(self._redact)
        self._http = httpx.Client(
            base_url=API_URL,
            timeout=REQUEST_TIMEOUT,
            transport=transport,  # None = real network; a fake server in tests.
            follow_redirects=False,  # Never follow: the token is in the path.
        )

    def send(self, text: str) -> None:
        """Send one HTML message. Raises a TelegramError subclass, never an httpx error."""
        body = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},  # A dozen links: one preview card would be noise.
        }
        try:
            response = self._http.post(f"/bot{self._token}/sendMessage", json=body)
        # `from None` everywhere: the httpx error holds the URL, so the token. Not even chained.
        except httpx.TimeoutException as exc:
            raise TelegramTemporaryError(f"Telegram request timed out ({type(exc).__name__})") from None
        except httpx.TransportError as exc:
            raise TelegramTemporaryError(f"Telegram unreachable ({type(exc).__name__})") from None

        try:
            data = response.json()
        except ValueError:
            data = None
        if isinstance(data, dict) and data.get("ok") is True:
            return
        raise self._error(response.status_code, data)

    def _error(self, status: int, data: object) -> TelegramError:
        """The TelegramError matching a refusal. Telegram's description is cleaned and checked for the token."""
        details = data if isinstance(data, dict) else {}
        code = details.get("error_code") if isinstance(details.get("error_code"), int) else status
        description = clean_text(str(details.get("description") or "no details"), 200) or "no details"
        description = description.replace(self._token, "<token>")  # Belt and braces: never echo the token.
        message = f"Telegram refused the message (HTTP {code}): {description}"

        if code == 429 or code >= 500:
            parameters = details.get("parameters")
            retry_after = parameters.get("retry_after") if isinstance(parameters, dict) else None
            return TelegramTemporaryError(message, retry_after if isinstance(retry_after, (int, float)) else None)
        if code in (401, 403, 404) or 300 <= code < 400:
            return TelegramFatalError(message)
        return TelegramError(message)  # 400 and the like: about this message only.

    def close(self) -> None:
        self._http.close()
        logging.getLogger("httpx").removeFilter(self._redact)

    def __enter__(self) -> "TelegramClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


# --- Sending a digest ---


@dataclass(frozen=True)
class DeliveryReport:
    """What happened to the digest messages, for main()."""

    total: int  # Messages to send.
    sent: int  # Confirmed by Telegram (their articles were reported through on_sent).
    failed: int  # Refused one by one (e.g. invalid HTML); their articles stay unsent.
    stop_reason: str | None = None  # Why sending stopped early, or None.

    @property
    def complete(self) -> bool:
        return self.sent == self.total


def send_digest(
    client: TelegramClient,
    messages: Sequence[OutgoingMessage],
    on_sent: Callable[[tuple[int, ...]], None],
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> DeliveryReport:
    """Send the messages in order. After each one Telegram confirms, call on_sent(its article ids).

    A message refused on its own (TelegramError) is skipped and the others go on. A fatal error, or a
    temporary one that outlasts the retries, stops sending: the remaining articles stay unsent and
    compete again for the next digest. Never raises a TelegramError.
    """
    sent = failed = 0
    for number, message in enumerate(messages, start=1):
        try:
            _send_with_retry(client, message.text, sleep)
        except (TelegramTemporaryError, TelegramFatalError) as error:  # Before TelegramError: subclasses.
            reason = f"{type(error).__name__}: {error}"
            logger.error("Digest sending stopped at message %d/%d: %s", number, len(messages), reason)
            return DeliveryReport(total=len(messages), sent=sent, failed=failed, stop_reason=reason)
        except TelegramError as error:
            failed += 1
            logger.warning("Digest message %d/%d refused, skipped: %s", number, len(messages), error)
            continue
        sent += 1
        if message.article_ids:
            on_sent(message.article_ids)
    return DeliveryReport(total=len(messages), sent=sent, failed=failed)


def _send_with_retry(client: TelegramClient, text: str, sleep: Callable[[float], None]) -> None:
    """client.send(text), retried after RETRY_DELAYS (or Telegram's capped retry_after) on temporary errors."""
    attempts = len(RETRY_DELAYS) + 1
    for attempt, default_delay in enumerate(RETRY_DELAYS, start=1):
        try:
            client.send(text)
            return
        except TelegramTemporaryError as error:
            delay = min(error.retry_after, MAX_RETRY_AFTER) if error.retry_after is not None else default_delay
            logger.warning("Telegram: %s, attempt %d/%d, retrying in %.1f s", error, attempt, attempts, delay)
            sleep(delay)
    client.send(text)  # Last attempt: its error propagates as is.
