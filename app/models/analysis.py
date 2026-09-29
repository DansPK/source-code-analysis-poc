"""Context, AI analysis, and the finished report item (spec §7–§13).

`AIAnalysis` is the schema the LLM must fill. Its enums are `Literal`s on purpose: a model
that invents a status fails validation here rather than propagating a made-up verdict into
the report. The Validator's job (spec §10) is then narrow -- downgrade what is doubtful, and
never upgrade anything.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.models.finding import Finding
from app.models.repository import Symbol

Status = Literal[
    "Likely Vulnerable",
    "Possible Vulnerability",
    "Likely False Positive",
    "Needs Manual Review",
]
Severity = Literal["Critical", "High", "Medium", "Low", "Info"]
Confidence = Literal["High", "Medium", "Low"]

# Report ordering and "can this be trusted" comparisons. Higher is more serious.
SEVERITY_ORDER: dict[str, int] = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1, "Info": 0}
CONFIDENCE_ORDER: dict[str, int] = {"High": 3, "Medium": 2, "Low": 1}

# The status a finding is given whenever the pipeline cannot stand behind a verdict:
# unparseable model output, failed validation, missing context. Never drop a finding
# silently -- park it here instead so a human sees it.
FALLBACK_STATUS: Status = "Needs Manual Review"


class CodeExcerpt(BaseModel):
    """A bounded slice of a file. Every excerpt reaching a prompt is truncated."""

    file: str = Field(description="Path relative to the repository root")
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str
    note: str | None = Field(default=None, description="Why this excerpt was included")
    truncated: bool = False


class FindingContext(BaseModel):
    """Everything gathered about one finding before the AI sees it (spec §5.6, §7).

    Bounded by `Settings.max_caller_depth`, `max_callee_depth` and `max_snippet_lines`.
    The bound is the design: it is what keeps the prompt small enough that the model
    reasons about a flow rather than a repository.
    """

    finding: Finding
    enclosing_function: Symbol | None = Field(
        default=None, description="The function containing the finding, if any"
    )
    function_source: str = Field(default="", description="Source of the enclosing function")

    callers: list[CodeExcerpt] = Field(default_factory=list)
    callees: list[CodeExcerpt] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list, description="Imports of the finding's file")
    related_files: list[CodeExcerpt] = Field(default_factory=list)

    # Ordered source -> sink chain of repository-relative paths, e.g.
    # ["routes/search.py", "services/search_service.py", "database/user_repository.py"].
    flow_chain: list[str] = Field(default_factory=list)
    reaches_entry_point: bool = Field(
        default=False, description="Whether the chain reaches a known external entry point"
    )

    # Project-level facts worth telling the model.
    primary_language: str = "unknown"
    frameworks: list[str] = Field(default_factory=list)


class AIAnalysis(BaseModel):
    """The LLM's structured verdict. Field list is spec §9, verbatim."""

    vulnerability_type: str
    status: Status
    severity: Severity
    confidence: Confidence

    source: str = Field(default="", description="The attacker-controlled input, e.g. request.args['q']")
    source_file: str = Field(default="")
    sink: str = Field(default="", description="The dangerous operation, e.g. cursor.execute()")
    sink_file: str = Field(default="")

    data_flow: list[str] = Field(
        default_factory=list, description="Ordered path from source to sink"
    )
    evidence: str = Field(default="", description="Why the model reached this verdict")
    protection_found: str = Field(
        default="",
        description="Sanitization, parameterization or authz observed; say so plainly if none",
    )
    impact: str = Field(default="", description="What an attacker could achieve")

    @property
    def is_reportable_as_vulnerability(self) -> bool:
        """True only for verdicts the report may present as an actual problem."""
        return self.status in ("Likely Vulnerable", "Possible Vulnerability")


class ReportItem(BaseModel):
    """One fully processed finding: detected, contextualized, judged, explained."""

    id: str = Field(description="Report-facing id, e.g. 'VULN-001'")
    finding: Finding
    context: FindingContext
    analysis: AIAnalysis

    # Produced by the agent (spec §11). Prose only -- the agent recommends, never patches.
    explanation: str = Field(default="")
    suggested_fix: str = Field(default="")

    @property
    def sort_key(self) -> tuple[int, int]:
        """Most severe, then most confident, first."""
        return (
            -SEVERITY_ORDER.get(self.analysis.severity, 0),
            -CONFIDENCE_ORDER.get(self.analysis.confidence, 0),
        )


class ScanReport(BaseModel):
    """The whole scan. What the JSON report and the API response both serialize."""

    repository_root: str
    origin: str | None = None
    primary_language: str = "unknown"
    frameworks: list[str] = Field(default_factory=list)

    files_scanned: int = 0
    candidates_found: int = Field(
        default=0, description="Raw findings from the scanner, before AI judgement"
    )
    items: list[ReportItem] = Field(default_factory=list)

    @property
    def counts_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.items:
            counts[item.analysis.status] = counts.get(item.analysis.status, 0) + 1
        return counts

    def sorted_items(self) -> list[ReportItem]:
        return sorted(self.items, key=lambda i: i.sort_key)
