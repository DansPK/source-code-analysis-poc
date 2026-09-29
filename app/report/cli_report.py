"""Human-readable report (spec §13)."""

from app.models import ReportItem, ScanReport

RULE = "=" * 72


def _item(item: ReportItem) -> str:
    analysis = item.analysis
    lines = [
        RULE,
        f"{item.id}  {analysis.vulnerability_type}",
        RULE,
        f"Status:      {analysis.status}",
        f"Severity:    {analysis.severity}          Confidence: {analysis.confidence}",
        "",
        f"Source:      {analysis.source or 'unknown'}"
        + (f"  ({analysis.source_file})" if analysis.source_file else ""),
        f"Sink:        {analysis.sink or 'unknown'}"
        f"  ({item.finding.file}:{item.finding.line})",
    ]

    if analysis.data_flow:
        lines += ["", "Data flow:"]
        lines += [
            f"  {'  ' if i == 0 else '→ '}{step}" for i, step in enumerate(analysis.data_flow)
        ]

    if item.explanation:
        lines += ["", "What happens:", *_wrap(item.explanation)]
    if analysis.protection_found:
        lines += ["", "Protection found:", *_wrap(analysis.protection_found)]
    if item.suggested_fix:
        lines += ["", "Suggested fix:", *_wrap(item.suggested_fix)]

    return "\n".join(lines)


def _wrap(text: str, width: int = 76) -> list[str]:
    import textwrap

    out = []
    for paragraph in text.split("\n\n"):
        out += textwrap.wrap(paragraph.strip(), width=width, initial_indent="  ",
                             subsequent_indent="  ") or [""]
        out.append("")
    return out[:-1]


def render(report: ScanReport) -> str:
    if not report.items:
        return (
            f"Scanned {report.files_scanned} files in {report.repository_root}.\n"
            f"No candidate vulnerabilities were found."
        )

    counts: dict[str, int] = {}
    for item in report.items:
        counts[item.analysis.status] = counts.get(item.analysis.status, 0) + 1
    summary = ", ".join(f"{count} {status}" for status, count in counts.items())

    header = (
        f"Scanned {report.files_scanned} files in {report.repository_root}\n"
        f"{report.candidates_found} candidate finding(s) from the scanner → {summary}"
    )
    footer = (
        f"{RULE}\nThese statuses are the model's assessment, not a guarantee. Review "
        "anything\nmarked Needs Manual Review before acting on it."
    )
    return "\n\n".join([header, *[_item(i) for i in report.items], footer])
