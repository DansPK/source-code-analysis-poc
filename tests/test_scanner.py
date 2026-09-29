"""M4: Semgrep finds the concatenated SQL, and the parser normalizes it."""

from pathlib import Path

import pytest

from app.config.settings import Settings
from app.findings.deduplicator import deduplicate
from app.findings.parser import parse_semgrep
from app.models import Finding
from app.scanners import ScannerError
from app.scanners.semgrep_scanner import scan

SAMPLE = Path("tests/vulnerable_samples/flask_app").resolve()


@pytest.fixture(scope="module")
def findings():
    payload = scan(SAMPLE, Settings().semgrep_rules)
    return parse_semgrep(payload, SAMPLE)


def test_finds_the_concatenated_sql(findings):
    sinks = [f for f in findings if f.file == "database/user_repository.py"]
    assert len(sinks) == 1

    source = (SAMPLE / "database/user_repository.py").read_text().splitlines()
    expected_line = next(i for i, l in enumerate(source, 1) if "cursor.execute(query)" in l)
    assert sinks[0].line == expected_line


def test_safe_parameterized_query_is_not_flagged(findings):
    """The false-positive control: find_user_by_id must stay clean."""
    source = (SAMPLE / "database/user_repository.py").read_text().splitlines()
    safe_line = next(i for i, l in enumerate(source, 1) if "WHERE id = ?" in l)
    assert not [f for f in findings if f.line == safe_line]


def test_finding_is_normalized(findings):
    finding = findings[0]
    assert finding.vulnerability_type == "SQL Injection"
    assert not Path(finding.file).is_absolute()  # paths stay relative to the root
    assert "execute" in finding.code_snippet  # read from disk, not from Semgrep
    assert finding.scanner_severity == "WARNING"


def test_missing_rules_directory_is_reported_clearly():
    with pytest.raises(ScannerError, match="rules not found"):
        scan(SAMPLE, "rules/does-not-exist")


# --- parser and deduplicator, without running Semgrep --------------------------


def _result(path="a.py", line=1, check_id="r1", metadata=None):
    return {
        "check_id": check_id,
        "path": path,
        "start": {"line": line},
        "extra": {"severity": "ERROR", "message": "m", "metadata": metadata or {}},
    }


@pytest.mark.parametrize(
    "metadata,check_id,expected",
    [
        ({"vulnerability_type": "SQL Injection"}, "r", "SQL Injection"),
        ({"cwe": "CWE-78: OS Command Injection"}, "r", "OS Command Injection"),
        ({"cwe": ["CWE-22: Path Traversal"]}, "r", "Path Traversal"),  # registry uses a list
        ({}, "rules.semgrep.python-sqli-concat", "Python Sqli Concat"),  # last resort
    ],
)
def test_vulnerability_type_is_derived_from_whatever_the_rule_provides(
    metadata, check_id, expected, tmp_path
):
    payload = {"results": [_result(metadata=metadata, check_id=check_id)]}
    assert parse_semgrep(payload, tmp_path)[0].vulnerability_type == expected


def test_parser_tolerates_a_missing_file(tmp_path):
    """The snippet is best-effort; a file that cannot be read must not abort the scan."""
    payload = {"results": [_result(path=str(tmp_path / "gone.py"))]}
    assert parse_semgrep(payload, tmp_path)[0].code_snippet == ""


def test_deduplicate_keeps_one_per_location_and_rule():
    def finding(id_, line, rule):
        return Finding(
            id=id_, file="a.py", line=line, rule_id=rule,
            vulnerability_type="t", scanner_severity="WARNING", message="m",
        )

    unique = deduplicate([
        finding("F-001", 10, "sqli"),
        finding("F-002", 10, "sqli"),   # same location and rule -> dropped
        finding("F-003", 10, "xss"),    # same location, different rule -> kept
        finding("F-004", 20, "sqli"),
    ])
    assert [f.id for f in unique] == ["F-001", "F-003", "F-004"]


def test_vendored_directories_are_not_scanned(tmp_path):
    """Disabling Semgrep's ignore files also drops .gitignore, so the skip list has
    to be passed explicitly -- otherwise a scan walks .venv and node_modules."""
    vulnerable = 'def f(name):\n    cursor.execute("SELECT * FROM t WHERE n = " + name)\n'
    (tmp_path / "app.py").write_text(vulnerable)
    for vendored in (".venv", "node_modules"):
        (tmp_path / vendored).mkdir()
        (tmp_path / vendored / "dep.py").write_text(vulnerable)

    findings = parse_semgrep(scan(tmp_path, Settings().semgrep_rules), tmp_path)

    assert [f.file for f in findings] == ["app.py"]
