"""M7: the agent's prose and the finished report, plus one end-to-end run."""

import json

import pytest

from app.agent.explainer import explain
from app.agent.remediation import recommend_fix
from app.agent.security_agent import report_item
from app.ai import AIError
from app.config.settings import Settings
from app.models import AIAnalysis, Finding, FindingContext, ReportItem, ScanReport
from app.report import reporter
from app.main import run_scan

ANALYSIS = AIAnalysis(
    vulnerability_type="SQL Injection",
    status="Likely Vulnerable",
    severity="High",
    confidence="High",
    source="an HTTP request parameter",
    source_file="routes/search.py",
    sink="execute()",
    sink_file="database/user_repository.py",
    data_flow=["routes/search.py", "database/user_repository.py"],
    evidence="Concatenated with no parameterization.",
    protection_found="None found.",
    impact="Arbitrary rows readable.",
)


class FakeClient:
    def __init__(self, reply=None, error=None):
        self.reply, self.error = reply or {}, error
        self.tasks = []

    def complete_json(self, system, user):
        self.tasks.append(next(l for l in user.splitlines() if l.startswith("TASK:")))
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture
def context():
    return FindingContext(
        finding=Finding(
            id="F-001", file="database/user_repository.py", line=17,
            rule_id="python-sqli-concat", vulnerability_type="SQL Injection",
            scanner_severity="WARNING", message="Concatenated SQL.",
        ),
        function_source="def search_users_by_name(name): ...",
        flow_chain=["routes/search.py", "database/user_repository.py"],
    )


def item(analysis=ANALYSIS, id_="VULN-001", explanation="what happens", fix="do this") -> ReportItem:
    return ReportItem(
        id=id_,
        finding=Finding(
            id="F-001", file="database/user_repository.py", line=17, rule_id="r",
            vulnerability_type=analysis.vulnerability_type, scanner_severity="WARNING",
            message="m",
        ),
        context=FindingContext(
            finding=Finding(
                id="F-001", file="database/user_repository.py", line=17, rule_id="r",
                vulnerability_type=analysis.vulnerability_type, scanner_severity="WARNING",
                message="m",
            )
        ),
        analysis=analysis,
        explanation=explanation,
        suggested_fix=fix,
    )


# --- agent ----------------------------------------------------------------------


def test_explanation_and_fix_are_asked_for_separately(context):
    """Two calls, each labelled, so the model does one job at a time."""
    client = FakeClient({"explanation": "E", "suggested_fix": "F"})

    result = report_item(client, 1, context, ANALYSIS)

    assert client.tasks == ["TASK: explanation", "TASK: remediation"]
    assert result.id == "VULN-001"
    assert result.explanation == "E" and result.suggested_fix == "F"


def test_agent_failure_leaves_prose_empty_rather_than_losing_the_finding(context):
    client = FakeClient(error=AIError("offline"))

    result = report_item(client, 2, context, ANALYSIS)

    assert result.id == "VULN-002"
    assert result.explanation == "" and result.suggested_fix == ""
    assert result.analysis == ANALYSIS  # the verdict survives


def test_agent_prompts_carry_the_flow_and_the_code(context):
    client = FakeClient({"explanation": "E"})
    explain(client, context, ANALYSIS)
    recommend_fix(client, context, ANALYSIS)
    assert len(client.tasks) == 2


# --- ordering and rendering -----------------------------------------------------


def test_worst_finding_comes_first():
    low = item(ANALYSIS.model_copy(update={"severity": "Low"}), "VULN-003")
    high_low_confidence = item(
        ANALYSIS.model_copy(update={"confidence": "Low"}), "VULN-002"
    )
    high = item(id_="VULN-001")

    assert [i.id for i in reporter.sort_items([low, high_low_confidence, high])] == [
        "VULN-001", "VULN-002", "VULN-003"
    ]


def test_cli_report_shows_the_flow_and_both_pieces_of_prose():
    rendered = reporter.render_cli(
        ScanReport(repository_root="/p", files_scanned=9, candidates_found=1, items=[item()])
    )
    assert "VULN-001  SQL Injection" in rendered
    assert "→ database/user_repository.py" in rendered
    assert "what happens" in rendered and "do this" in rendered
    assert "not a guarantee" in rendered  # the honesty note


def test_cli_report_says_so_when_nothing_was_found():
    rendered = reporter.render_cli(ScanReport(repository_root="/p", files_scanned=9))
    assert "No candidate vulnerabilities" in rendered


def test_json_report_round_trips(tmp_path):
    report = ScanReport(repository_root="/p", files_scanned=9, candidates_found=1, items=[item()])

    path = reporter.write_json(report, str(tmp_path))

    assert ScanReport.model_validate(json.loads(path.read_text())) == report


# --- end to end -----------------------------------------------------------------


def test_full_pipeline_on_the_fixture():
    """Every stage, source to report, with no API key."""
    report = run_scan(None, "tests/vulnerable_samples/flask_app", Settings(llm_mock=True))

    assert report.candidates_found == 1
    found = report.items[0]
    assert found.id == "VULN-001"
    assert found.analysis.status == "Likely Vulnerable"
    assert found.analysis.data_flow == [
        "routes/search.py", "services/search_service.py", "database/user_repository.py"
    ]
    assert found.explanation and found.suggested_fix
    # The agent recommends; it must never hand back rewritten code.
    assert "def search_users_by_name" not in found.suggested_fix
