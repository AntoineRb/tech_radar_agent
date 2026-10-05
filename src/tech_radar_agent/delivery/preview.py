"""Writing the digest to a local file instead of sending it: --dry-run and --preview.

    write_preview(messages, today, folder) -> Path   output/digest-YYYY-MM-DD.html

A browser shows Telegram HTML close to the real thing, but not exactly: summaries are folded in
Telegram and unfolded here. The real rendering is checked by sending. The messages are already escaped
Telegram HTML (agent/render.py), so they go into the page as they are.
"""

from collections.abc import Sequence
from datetime import date
from pathlib import Path

from tech_radar_agent.delivery.telegram import OutgoingMessage

DEFAULT_FOLDER = Path("output")  # Git-ignored.

PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tech Radar digest, {day}</title>
<style>
  body {{ font: 15px/1.45 -apple-system, "Segoe UI", sans-serif; max-width: 640px; margin: 2em auto; padding: 0 16px; }}
  .message {{ white-space: pre-wrap; padding: 12px 14px; margin: 0 0 12px; border-radius: 12px; background: #f2f2f2; }}
  blockquote {{ margin: .3em 0; padding-left: .8em; border-left: 3px solid #3a8; }}
  .note {{ color: #777; font-size: 13px; }}
</style>
<p class="note">Preview of the digest: not sent, nothing marked as sent. Telegram folds the summaries; a browser
does not.</p>
{messages}
"""


def write_preview(messages: Sequence[OutgoingMessage], today: date, folder: Path = DEFAULT_FOLDER) -> Path:
    """Write the messages as one HTML page, one box per Telegram message. Return the file written."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"digest-{today.isoformat()}.html"
    boxes = "\n".join(f'<div class="message">{message.text}</div>' for message in messages)
    path.write_text(PAGE.format(day=today.isoformat(), messages=boxes), encoding="utf-8")
    return path
