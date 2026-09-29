"""Context, AI verdict, and report (spec §7–§13).

`AIAnalysis` is the schema the LLM must fill. Its enums are `Literal`s on purpose: a
model that invents a status fails validation here instead of putting a made-up verdict
in the report.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.models.finding import Finding

Status = Literal[
    "Likely Vulnerable",
    "Possible Vulnerability",
    "Likely False Positive",
    "Needs Manual Review",
]
Severity = Literal["Critical", "High", "Medium", "Low", "Info"]
Confidence = Literal["High", "Medium", "Low"]


class CodeExcerpt(BaseModel):
    file: str
    start_line: int
    end_line: int
    content: str


class FindingContext(BaseModel):
    """What the AI is shown about one finding (spec §5.6, §7).

    Bounded by the `max_*` settings. The bound is the design: it keeps the prompt to a
    flow rather than a repository.
    """

    finding: Finding
    function_source: str = ""  # the function containing the finding
    imports: list[str] = Field(default_factory=list)
    callers: list[CodeExcerpt] = Field(default_factory=list)
    callees: list[CodeExcerpt] = Field(default_factory=list)
    # Ordered source -> sink chain, e.g. ["routes/search.py", "database/user_repository.py"]
    flow_chain: list[str] = Field(default_factory=list)


class AIAnalysis(BaseModel):
    """The LLM's structured verdict. Field list is spec §9, verbatim."""

    vulnerability_type: str
    status: Status
    severity: Severity
    confidence: Confidence
    source: str = ""  # e.g. request.args["q"]
    source_file: str = ""
    sink: str = ""  # e.g. cursor.execute()
    sink_file: str = ""
    data_flow: list[str] = Field(default_factory=list)
    evidence: str = ""
    protection_found: str = ""
    impact: str = ""


class ReportItem(BaseModel):
    """One finding: detected, contextualized, judged, explained."""

    id: str  # e.g. "VULN-001"
    finding: Finding
    context: FindingContext
    analysis: AIAnalysis
    explanation: str = ""  # agent prose; it recommends, never patches
    suggested_fix: str = ""


class ScanReport(BaseModel):
    """The whole scan -- what the JSON report and the API response serialize."""

    repository_root: str
    files_scanned: int = 0
    candidates_found: int = 0  # raw scanner findings, before AI judgement
    items: list[ReportItem] = Field(default_factory=list)
