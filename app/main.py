"""CLI entry point.

`run_scan()` is the one place the pipeline is wired together. This CLI and the FastAPI
layer in `app/api/` are both thin adapters over it -- keep it that way.

The argument surface below is final; the stages inside `run_scan()` are filled in by
later milestones (see HANDOFF.md).
"""

import argparse
import sys
from pathlib import Path

from app.config.settings import Settings, get_settings
from app.findings.deduplicator import deduplicate
from app.findings.parser import parse_semgrep
from app.repository.analyzer import analyze
from app.scanners import ScannerError
from app.scanners.semgrep_scanner import scan
from app.source import SourceError
from app.source.loader import load_source
from app.utils.logging import get_logger

logger = get_logger(__name__)


def run_scan(repo: str | None, path: str | None, settings: Settings):
    """Run the full pipeline and return a ScanReport.

    Stage order follows the spec and must stay visible here: source -> repository
    analysis -> static scan -> finding parse -> context -> AI analysis -> validation
    -> agent -> report.
    """
    repository = load_source(repo, path, settings)
    logger.info("Source: %s%s", repository.root, f" (from {repository.origin})" if repository.origin else "")

    code_map = analyze(repository)

    payload = scan(Path(repository.root), settings.semgrep_rules)
    findings = deduplicate(parse_semgrep(payload, Path(repository.root)))
    logger.info("Candidate findings: %d", len(findings))

    raise NotImplementedError("Pipeline stages land in M5-M7; see HANDOFF.md.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scan", description="AI source-code vulnerability scanner (POC).")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--repo", metavar="URL", help="Git repository URL to clone and scan")
    source.add_argument("--path", metavar="PATH", help="Local directory or file to scan")
    parser.add_argument("--format", choices=("cli", "json"), default="cli", help="Report format")
    parser.add_argument("--out", metavar="DIR", help="Directory to write a JSON report into")
    parser.add_argument("--mock", action="store_true", help="Use canned LLM responses (no API key)")
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.mock:
        settings.llm_mock = True

    try:
        run_scan(args.repo, args.path, settings)
    except (SourceError, ScannerError) as exc:
        logger.error("%s", exc)
        return 2
    except NotImplementedError as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
