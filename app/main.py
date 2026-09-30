"""CLI entry point.

`run_scan()` is the one place the pipeline is wired together. This CLI and the FastAPI
layer in `app/api/` are both thin adapters over it -- keep it that way.
"""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from app.agent.security_agent import report_item
from app.ai import AIError
from app.ai.analyzer import analyze as analyze_finding
from app.ai.client import get_client
from app.ai.validator import validate
from app.config.settings import Settings, get_settings
from app.context.builder import build_context
from app.findings.deduplicator import deduplicate
from app.findings.parser import parse_semgrep
from app.models import AIAnalysis, Finding, ReportItem, ScanReport
from app.report import reporter
from app.repository.analyzer import analyze
from app.scanners import ScannerError
from app.scanners.semgrep_scanner import scan
from app.source import SourceError
from app.source.loader import load_source
from app.utils.logging import get_logger

logger = get_logger(__name__)


def run_scan(
    repo: str | None,
    path: str | None,
    settings: Settings,
    on_analysis: Callable[[int, int, Finding, AIAnalysis], None] | None = None,
    on_text: Callable[[int, str, str], None] | None = None,
    on_item: Callable[[int, int, ReportItem], None] | None = None,
    *,
    branch: str | None = None,
    archive: str | None = None,
    subpath: str | None = None,
) -> ScanReport:
    """Run the full pipeline. The stage order is the spec's, and stays visible here.

    The callbacks let the MCP server stream a scan that takes minutes. Each gets the
    finding's number (1-based, as in VULN-001): `on_analysis(number, total, finding,
    analysis)` once the verdict is in, `on_text(number, field, text)` as the explanation
    and suggested fix are written, and `on_item(number, total, item)` when it is complete.
    `branch`, `archive` and `subpath` are passed to `load_source()`.
    """
    repository = load_source(
        repo, path, settings, branch=branch, archive=archive, subpath=subpath
    )
    logger.info("Source: %s", repository.root)

    code_map = analyze(repository)
    root = Path(repository.root)

    findings = deduplicate(parse_semgrep(scan(root, settings.semgrep_configs), root))
    logger.info("Candidate findings: %d", len(findings))

    client = get_client(settings)
    items = []
    for number, finding in enumerate(findings, start=1):
        context = build_context(repository, code_map, finding, settings)
        analysis = validate(analyze_finding(client, context, repository), context, repository)
        if on_analysis:
            on_analysis(number, len(findings), finding, analysis)
        text = (lambda field, piece, n=number: on_text(n, field, piece)) if on_text else None
        items.append(report_item(client, number, context, analysis, text))
        logger.info(
            "  %s: %s (%s severity, %s confidence)",
            items[-1].id, analysis.status, analysis.severity, analysis.confidence,
        )
        if on_item:
            on_item(number, len(findings), items[-1])

    return ScanReport(
        repository_root=repository.root,
        files_scanned=len(repository.files),
        candidates_found=len(findings),
        items=reporter.sort_items(items),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scan", description="AI source-code vulnerability scanner (POC)."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--repo", metavar="URL", help="Git repository URL to clone and scan")
    source.add_argument(
        "--path", metavar="PATH",
        help="Local directory or file to scan (default: the current directory)",
    )
    parser.add_argument("--format", choices=("cli", "json"), default="cli", help="Report format")
    parser.add_argument("--out", metavar="DIR", help="Directory to write a JSON report into")
    args = parser.parse_args(argv)

    settings = get_settings()

    try:
        report = run_scan(args.repo, args.path or (None if args.repo else "."), settings)
    except (SourceError, ScannerError, AIError) as exc:
        logger.error("%s", exc)
        return 2

    if args.format == "json" or args.out:
        logger.info("Wrote %s", reporter.write_json(report, args.out or settings.reports_dir))
    if args.format == "cli":
        print(reporter.render_cli(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
