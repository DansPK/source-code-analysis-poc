"""Keep the report honest (spec §10).

The validator only ever *lowers* a verdict. It never raises severity or confidence, and
never deletes a finding -- anything it cannot stand behind becomes "Needs Manual Review"
so a human still sees it.
"""

from app.models import AIAnalysis, FindingContext, Repository
from app.utils.logging import get_logger

logger = get_logger(__name__)

CLAIMS_VULNERABLE = ("Likely Vulnerable", "Possible Vulnerability")


def validate(analysis: AIAnalysis, context: FindingContext, repository: Repository) -> AIAnalysis:
    known_files = {source_file.path for source_file in repository.files}
    problems = []

    # A path the model named but the project does not contain means the reasoning is
    # not grounded in this codebase.
    for field in ("source_file", "sink_file"):
        named = getattr(analysis, field)
        if named and known_files and named not in known_files:
            problems.append(f"{field} '{named}' is not a file in this project")

    for named in analysis.data_flow:
        if known_files and named not in known_files:
            problems.append(f"data_flow mentions '{named}', which is not a file in this project")
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
                f"{analysis.evidence}\n\n"
                f"[Downgraded automatically: {'; '.join(problems)}.]"
            ).strip(),
        }
    )
