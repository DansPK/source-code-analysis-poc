"""Contract tests: the enums must reject a hallucinated LLM verdict."""

import pytest
from pydantic import ValidationError

from app.models import AIAnalysis, Finding, FindingContext, ReportItem

ANALYSIS = {
    "vulnerability_type": "SQL Injection",
    "status": "Likely Vulnerable",
    "severity": "High",
    "confidence": "High",
    "source": 'request.args["q"]',
    "source_file": "routes/search.py",
    "sink": "cursor.execute()",
    "sink_file": "database/user_repository.py",
    "data_flow": ["routes/search.py", "database/user_repository.py"],
    "evidence": "Concatenated into the statement with no parameterization.",
    "protection_found": "None found.",
    "impact": "Arbitrary rows could be read or modified.",
}

FINDING = {
    "id": "F-001",
    "file": "database/user_repository.py",
    "line": 17,
    "rule_id": "python-sqli-concat",
    "vulnerability_type": "SQL Injection",
    "scanner_severity": "WARNING",
    "message": "String concatenation in a SQL statement.",
}


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("status", "Definitely Exploitable"),  # plausible hallucination
        ("status", "likely vulnerable"),  # right words, wrong case
        ("severity", "Severe"),
        ("confidence", "Very High"),
    ],
)
def test_invalid_enum_values_are_rejected(field, bad_value):
    with pytest.raises(ValidationError):
        AIAnalysis.model_validate(ANALYSIS | {field: bad_value})


@pytest.mark.parametrize(
    "status",
    ["Likely Vulnerable", "Possible Vulnerability", "Likely False Positive", "Needs Manual Review"],
)
def test_all_spec_statuses_are_accepted(status):
    assert AIAnalysis.model_validate(ANALYSIS | {"status": status}).status == status


def test_report_item_assembles():
    """The shape M7 produces, from a raw dict like the LLM returns."""
    item = ReportItem(
        id="VULN-001",
        finding=Finding(**FINDING),
        context=FindingContext(finding=Finding(**FINDING)),
        analysis=AIAnalysis.model_validate(ANALYSIS),
    )
    assert item.analysis.data_flow[-1] == item.finding.file
