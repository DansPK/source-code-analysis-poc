"""Semgrep JSON -> Finding. This is where Semgrep stops existing.

Nothing after this module sees Semgrep's shapes, so adding another scanner means
writing another parser and changing nothing else.
"""

from pathlib import Path

from app.models import Finding
from app.utils.logging import get_logger

logger = get_logger(__name__)

SNIPPET_CONTEXT_LINES = 2


def _relative(path: str, root: Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    try:
        return str(candidate.relative_to(root))
    except ValueError:
        return path  # outside the project; keep whatever Semgrep said


def _snippet(root: Path, relative_path: str, line: int) -> str:
    """Read the matched line and its neighbours.

    Semgrep's own `extra.lines` is the string "requires login" in the OSS engine, so
    the snippet has to come from disk.
    """
    try:
        lines = (root / relative_path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return ""
    start = max(0, line - 1 - SNIPPET_CONTEXT_LINES)
    return "\n".join(lines[start : line + SNIPPET_CONTEXT_LINES])


def _vulnerability_type(metadata: dict, rule_id: str) -> str:
    """A human label. Our rules state it; registry rules carry a CWE instead."""
    if metadata.get("vulnerability_type"):
        return metadata["vulnerability_type"]
    cwe = metadata.get("cwe")
    if isinstance(cwe, list):
        cwe = cwe[0] if cwe else None
    if cwe:
        # "CWE-89: SQL Injection" -> "SQL Injection"
        return str(cwe).split(":", 1)[-1].strip()
    return rule_id.rsplit(".", 1)[-1].replace("-", " ").replace("_", " ").title()


def parse_semgrep(payload: dict, root: Path) -> list[Finding]:
    findings = []
    for number, result in enumerate(payload.get("results", []), start=1):
        extra = result.get("extra", {})
        metadata = extra.get("metadata", {})
        relative_path = _relative(result["path"], root)
        line = result["start"]["line"]

        findings.append(
            Finding(
                id=f"F-{number:03d}",
                file=relative_path,
                line=line,
                rule_id=result["check_id"],
                vulnerability_type=_vulnerability_type(metadata, result["check_id"]),
                scanner_severity=extra.get("severity", "INFO"),
                message=extra.get("message", "").strip(),
                code_snippet=_snippet(root, relative_path, line),
            )
        )

    for error in payload.get("errors", []):
        # Some messages embed the whole file Semgrep failed on; the first line says enough.
        message = str(error.get("message", error)).strip().splitlines()
        logger.warning("Semgrep: %s", message[0] if message else error)

    return findings
