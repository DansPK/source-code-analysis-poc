"""Keep the report honest (spec §10).

The validator only ever *lowers* a verdict. It never raises severity or confidence, and
never deletes a finding -- anything it cannot stand behind becomes "Needs Manual Review"
so a human still sees it.

Its one real job is catching claims that are not grounded in this codebase. That check
has to be forgiving about *form*: models legitimately answer with
"routes/search.py:11 (request.args['q'])" rather than a bare path, and downgrading a
correct analysis for being more informative is worse than not checking at all.
"""

from pathlib import Path

from app.models import AIAnalysis, FindingContext, Repository
from app.repository.language_detector import EXTENSIONS
from app.utils.logging import get_logger

logger = get_logger(__name__)

CLAIMS_VULNERABLE = ("Likely Vulnerable", "Possible Vulnerability")


def _claimed_file(text: str) -> str | None:
    """The file path a model's answer refers to, or None if it names no file.

    Accepts "routes/search.py", "routes/search.py:11" and
    "routes/search.py:11 (q = request.args['q'])" alike.
    """
    token = text.strip().split(":", 1)[0].split()[0].strip("`'\"") if text.strip() else ""
    if not token:
        return None
    looks_like_a_path = "/" in token or Path(token).suffix.lower() in EXTENSIONS
    return token if looks_like_a_path else None


def validate(analysis: AIAnalysis, context: FindingContext, repository: Repository) -> AIAnalysis:
    known_files = {source_file.path for source_file in repository.files}
    if not known_files:
        return analysis

    problems = []

    # A file the model names that this project does not contain means the reasoning is
    # not grounded in this codebase. Steps that name no file at all are prose, and fine.
    for label, text in (
        ("source_file", analysis.source_file),
        ("sink_file", analysis.sink_file),
        *[("data_flow", step) for step in analysis.data_flow],
    ):
        claimed = _claimed_file(text)
        if claimed and claimed not in known_files:
            problems.append(f"{label} names '{claimed}', which is not a file in this project")
            break

    # A vulnerable verdict has to be argued for.
    if analysis.status in CLAIMS_VULNERABLE and not analysis.evidence.strip():
        problems.append("a vulnerable verdict was given with no evidence")

    if not problems:
        return analysis

    logger.warning("Downgrading %s: %s", context.finding.id, "; ".join(problems))
    return analysis.model_copy(
        update={
            "status": "Needs Manual Review",
            "confidence": "Low",
            "evidence": (
                f"{analysis.evidence}\n\n[Downgraded automatically: {'; '.join(problems)}.]"
            ).strip(),
        }
    )
