"""Ordering and output-format dispatch."""

from app.models import ReportItem, ScanReport
from app.report import cli_report, json_report

# Most serious first. The report's job is to put the worst thing at the top.
SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4}
CONFIDENCE_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def sort_items(items: list[ReportItem]) -> list[ReportItem]:
    return sorted(
        items,
        key=lambda i: (
            SEVERITY_ORDER.get(i.analysis.severity, 99),
            CONFIDENCE_ORDER.get(i.analysis.confidence, 99),
            i.id,
        ),
    )


def render_cli(report: ScanReport) -> str:
    return cli_report.render(report)


def write_json(report: ScanReport, out_dir: str):
    return json_report.write(report, out_dir)
