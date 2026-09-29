"""CLI for asking questions about a project."""

import argparse
import sys

from app.agent.ask import ask
from app.ai import AIError
from app.ai.client import get_client
from app.config.settings import get_settings
from app.repository.analyzer import analyze
from app.source import SourceError
from app.source.loader import load_source
from app.utils.logging import get_logger

logger = get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ask", description="Ask questions about a source project."
    )
    parser.add_argument(
        "--path", default=".", metavar="PATH",
        help="Project to ask about (default: the current directory)",
    )
    parser.add_argument(
        "question", nargs="*", help="Your question; omit to open the interactive TUI"
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    try:
        repository = load_source(None, args.path, settings)
        code_map = analyze(repository)
        client = get_client(settings)
    except (SourceError, AIError) as exc:
        logger.error("%s", exc)
        return 2

    if args.question:
        answer, _ = ask(
            client, repository, code_map, " ".join(args.question),
            max_steps=settings.max_ask_steps,
        )
        print(answer)
        return 0

    from app.tui import AskApp

    AskApp(client, repository, code_map, settings).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
