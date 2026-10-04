"""Send one message to the configured LLM, to check that the setup works.

    uv run --env-file .env python -m tech_radar_agent.llm "Reply with just the word: pong"
    uv run --env-file .env python -m tech_radar_agent.llm --debug "..."    # also log duration and tokens

Exit codes: 0 answer printed, 1 the LLM failed, 2 invalid settings.
"""

import argparse
import logging
import sys
import time

from tech_radar_agent.llm.client import LlmClient, LlmError
from tech_radar_agent.llm.settings import load_llm_settings

DEFAULT_PROMPT = "Reply with just the word: pong"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tech_radar_agent.llm", description=__doc__.splitlines()[0])
    parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT, help=f'default: "{DEFAULT_PROMPT}"')
    parser.add_argument("--debug", action="store_true", help="log duration and token usage")
    args = parser.parse_args(argv)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
        logging.getLogger("httpcore").setLevel(logging.WARNING)  # Too verbose at DEBUG.

    try:
        settings = load_llm_settings()
    except ValueError as error:
        print(f"Invalid LLM settings: {error}", file=sys.stderr)
        return 2

    print(f"Model {settings.model} at {settings.base_url}", file=sys.stderr)  # Never the key.
    started = time.perf_counter()
    try:
        with LlmClient(settings) as llm:
            answer = llm.chat([{"role": "user", "content": args.prompt}])
    except LlmError as error:
        print(f"LLM error: {error}", file=sys.stderr)
        return 1

    print(answer)
    print(f"({time.perf_counter() - started:.1f} s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
