"""Collapse repeats.

Overlapping rules report the same line more than once; the AI stage is the expensive
part of the pipeline, so pay for each distinct location only once.
"""

from app.models import Finding


def deduplicate(findings: list[Finding]) -> list[Finding]:
    seen = set()
    unique = []
    for finding in findings:
        key = (finding.file, finding.line, finding.rule_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique
