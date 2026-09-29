"""CLI entry point.

`run_scan()` is the single place the pipeline is wired together. The CLI here and
the FastAPI layer in `app/api/` are both thin adapters over it -- keep it that way.

Milestone status: the argument surface below is final; the stages inside
`run_scan()` are filled in by later milestones (see HANDOFF.md).
"""

import argparse
import sys

from app.config.settings import Settings, get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scan",
        description="AI source-code vulnerability scanner (POC).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--repo", metavar="URL", help="Git repository URL to clone and scan")
    source.add_argument("--path", metavar="PATH", help="Local directory or file to scan")

    parser.add_argument(
        "--format",
        choices=("cli", "json"),
        default="cli",
        help="Report format (default: cli)",
    )
    parser.add_argument("--out", metavar="DIR", help="Directory to write a JSON report into")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use canned LLM responses instead of a real API (no key required)",
    )
    return parser


def run_scan(
    *,
    repo: str | None = None,
    path: str | None = None,
    settings: Settings | None = None,
) -> list:
    """Run the full pipeline and return the report items.

    Stage order follows the POC spec and must stay visible here:
    source -> repository analysis -> static scan -> finding parse -> context
    -> AI analysis -> validation -> agent -> report.
    """
    settings = settings or get_settings()
    raise NotImplementedError(
        "Pipeline stages land in milestones M2-M7; see HANDOFF.md for the current one."
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    settings = get_settings()
    if args.mock:
        settings = settings.model_copy(update={"llm_mock": True})

    try:
        run_scan(repo=args.repo, path=args.path, settings=settings)
    except NotImplementedError as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
