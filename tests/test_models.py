"""M1 contract tests.

These lock the behaviour later milestones depend on: the enums reject invalid values
(so a hallucinated LLM verdict fails here rather than reaching the report), and the
small helpers on the code map and report models do what their callers assume.
"""

import pytest
from pydantic import ValidationError

from app.models import (
    AIAnalysis,
    CodeExcerpt,
    CodeMap,
    FileNode,
    Finding,
    FindingContext,
    Repository,
    ReportItem,
    ScanReport,
    SourceFile,
    Symbol,
)


# --- fixtures ------------------------------------------------------------------


@pytest.fixture
def finding() -> Finding:
    return Finding(
        id="F-001",
        file="database/user_repository.py",
        line=17,
        rule_id="python-sqli-concat",
        vulnerability_type="SQL Injection",
        scanner_severity="WARNING",
        message="Detected string concatenation in a SQL statement.",
        code_snippet='query = "SELECT ... " + name',
    )


@pytest.fixture
def analysis() -> AIAnalysis:
    return AIAnalysis(
        vulnerability_type="SQL Injection",
        status="Likely Vulnerable",
        severity="High",
        confidence="High",
        source='request.args["q"]',
        source_file="routes/search.py",
        sink="cursor.execute()",
        sink_file="database/user_repository.py",
        data_flow=[
            "routes/search.py",
            "services/search_service.py",
            "database/user_repository.py",
        ],
        evidence="The value is concatenated into the statement with no parameterization.",
        protection_found="None found.",
        impact="An attacker could read or modify arbitrary rows.",
    )


# --- Finding -------------------------------------------------------------------


def test_finding_location(finding):
    assert finding.location == "database/user_repository.py:17"


def test_finding_rejects_line_zero(finding):
    """Scanners are 1-indexed; a 0 means the parser mangled the offset."""
    with pytest.raises(ValidationError):
        Finding.model_validate(finding.model_dump() | {"line": 0})


def test_finding_defaults_to_semgrep(finding):
    assert finding.scanner == "semgrep"


# --- Repository and code map ---------------------------------------------------


def test_primary_language_picks_the_most_common():
    repo = Repository(root="/tmp/x", languages={"python": 9, "yaml": 2})
    assert repo.primary_language == "python"


def test_primary_language_unknown_when_empty():
    assert Repository(root="/tmp/x").primary_language == "unknown"


def test_symbol_contains_line():
    sym = Symbol(name="search_users_by_name", kind="function", file="db.py", line=10, end_line=20)
    assert sym.contains_line(10) and sym.contains_line(20) and sym.contains_line(15)
    assert not sym.contains_line(9) and not sym.contains_line(21)


def test_symbol_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        Symbol(name="x", kind="macro", file="a.py", line=1, end_line=2)


def test_enclosing_function_picks_the_innermost():
    outer = Symbol(name="outer", kind="function", file="a.py", line=1, end_line=50)
    inner = Symbol(name="inner", kind="function", file="a.py", line=10, end_line=20)
    node = FileNode(file="a.py", functions=[outer, inner])
    assert node.enclosing_function(15) is inner
    assert node.enclosing_function(30) is outer
    assert node.enclosing_function(80) is None


def test_code_map_resolves_symbols_and_callers():
    code_map = CodeMap(
        files={
            "services/search_service.py": FileNode(
                file="services/search_service.py",
                calls=["search_users_by_name"],
            ),
            "database/user_repository.py": FileNode(
                file="database/user_repository.py",
                functions=[
                    Symbol(
                        name="search_users_by_name",
                        kind="function",
                        file="database/user_repository.py",
                        line=13,
                        end_line=20,
                    )
                ],
                # A file calling a symbol it also defines is not its own caller.
                calls=["search_users_by_name"],
            ),
        },
        symbol_index={"search_users_by_name": ["database/user_repository.py"]},
    )

    assert code_map.defining_files("search_users_by_name") == ["database/user_repository.py"]
    assert code_map.defining_files("nonexistent") == []
    assert code_map.callers_of("search_users_by_name") == ["services/search_service.py"]


# --- AIAnalysis: the enums that guard the LLM ----------------------------------


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("status", "Definitely Exploitable"),  # a plausible hallucination
        ("status", "likely vulnerable"),  # right words, wrong case
        ("severity", "Severe"),
        ("confidence", "Very High"),
    ],
)
def test_invalid_enum_values_are_rejected(analysis, field, bad_value):
    payload = analysis.model_dump() | {field: bad_value}
    with pytest.raises(ValidationError):
        AIAnalysis.model_validate(payload)


@pytest.mark.parametrize(
    "status",
    ["Likely Vulnerable", "Possible Vulnerability", "Likely False Positive", "Needs Manual Review"],
)
def test_all_spec_statuses_are_accepted(analysis, status):
    assert AIAnalysis.model_validate(analysis.model_dump() | {"status": status}).status == status


def test_only_vulnerable_statuses_are_reportable(analysis):
    assert analysis.is_reportable_as_vulnerability
    for status in ("Likely False Positive", "Needs Manual Review"):
        assert not AIAnalysis.model_validate(
            analysis.model_dump() | {"status": status}
        ).is_reportable_as_vulnerability


def test_analysis_parses_from_raw_json_like_the_llm_returns(analysis):
    """The analyzer feeds a plain dict straight from the model into this."""
    parsed = AIAnalysis.model_validate(analysis.model_dump(mode="json"))
    assert parsed == analysis


# --- Report ordering -----------------------------------------------------------


def _item(finding, analysis, id_, severity, confidence) -> ReportItem:
    return ReportItem(
        id=id_,
        finding=finding,
        context=FindingContext(finding=finding),
        analysis=AIAnalysis.model_validate(
            analysis.model_dump() | {"severity": severity, "confidence": confidence}
        ),
    )


def test_report_sorts_by_severity_then_confidence(finding, analysis):
    report = ScanReport(
        repository_root="/tmp/x",
        items=[
            _item(finding, analysis, "VULN-003", "Low", "High"),
            _item(finding, analysis, "VULN-002", "High", "Low"),
            _item(finding, analysis, "VULN-001", "High", "High"),
        ],
    )
    assert [i.id for i in report.sorted_items()] == ["VULN-001", "VULN-002", "VULN-003"]


def test_counts_by_status(finding, analysis):
    report = ScanReport(
        repository_root="/tmp/x",
        items=[
            _item(finding, analysis, "VULN-001", "High", "High"),
            _item(finding, analysis, "VULN-002", "Low", "Low"),
        ],
    )
    assert report.counts_by_status == {"Likely Vulnerable": 2}


# --- Context -------------------------------------------------------------------


def test_context_defaults_are_empty_not_none(finding):
    ctx = FindingContext(finding=finding)
    assert ctx.callers == [] and ctx.flow_chain == [] and ctx.enclosing_function is None
    assert ctx.reaches_entry_point is False


def test_excerpt_round_trips(finding):
    excerpt = CodeExcerpt(
        file="routes/search.py", start_line=1, end_line=5, content="q = request.args['q']"
    )
    ctx = FindingContext(finding=finding, related_files=[excerpt])
    assert FindingContext.model_validate(ctx.model_dump()).related_files[0].file == "routes/search.py"


def test_source_file_requires_nonnegative_loc():
    with pytest.raises(ValidationError):
        SourceFile(path="a.py", language="python", loc=-1)
