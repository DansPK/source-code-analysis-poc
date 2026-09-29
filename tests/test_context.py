"""M5: the cross-file walk from a sink back to where the data came from."""

from pathlib import Path

import pytest

from app.config.settings import Settings
from app.context.builder import build_context
from app.context.symbol_resolver import enclosing_function
from app.models import Finding
from app.repository.analyzer import analyze
from app.source.loader import load_source

SAMPLE = "tests/vulnerable_samples/flask_app"
SINK_FILE = "database/user_repository.py"


@pytest.fixture(scope="module")
def project():
    repository = load_source(None, SAMPLE, Settings())
    return repository, analyze(repository)


def line_of(relative_path: str, needle: str) -> int:
    lines = Path(SAMPLE, relative_path).read_text().splitlines()
    return next(i for i, line in enumerate(lines, 1) if needle in line)


def finding_at(relative_path: str, needle: str) -> Finding:
    return Finding(
        id="F-001",
        file=relative_path,
        line=line_of(relative_path, needle),
        rule_id="python-sqli-concat",
        vulnerability_type="SQL Injection",
        scanner_severity="WARNING",
        message="Concatenated SQL reaches execute().",
    )


@pytest.fixture
def context(project):
    repository, code_map = project
    return build_context(
        repository, code_map, finding_at(SINK_FILE, "cursor.execute(query)"), Settings()
    )


def test_flow_chain_runs_source_to_sink(context):
    """The spec's worked example, reproduced end to end."""
    assert context.flow_chain == [
        "routes/search.py",
        "services/search_service.py",
        "database/user_repository.py",
    ]


def test_context_reaches_the_real_source_in_another_file(context):
    """The whole point: the scanner saw line 17 of the database layer, but the
    attacker-controlled value is three files away."""
    caller_code = "\n".join(c.content for c in context.callers)
    assert 'request.args["q"]' in caller_code


def test_sink_function_and_its_callee_are_included(context):
    assert "cursor.execute(query)" in context.function_source
    assert any("_connect" in c.content for c in context.callees)


def test_finding_in_an_entry_point_has_a_single_step_chain(project):
    repository, code_map = project
    context = build_context(
        repository, code_map, finding_at("routes/search.py", "request.args"), Settings()
    )
    assert context.flow_chain == ["routes/search.py"]


def test_module_level_finding_does_not_crash(project):
    """A finding outside any function still yields usable context."""
    repository, code_map = project
    context = build_context(
        repository, code_map, finding_at(SINK_FILE, "DB_PATH ="), Settings()
    )
    assert context.function_source == ""
    assert context.flow_chain == [SINK_FILE]
    assert context.imports == ["sqlite3"]


def test_caller_depth_bound_is_respected(project):
    """The bound is the design -- one level up stops at the service layer."""
    repository, code_map = project
    context = build_context(
        repository,
        code_map,
        finding_at(SINK_FILE, "cursor.execute(query)"),
        Settings(max_caller_depth=1),
    )
    assert context.flow_chain == ["services/search_service.py", SINK_FILE]


def test_excerpts_are_truncated(project):
    repository, code_map = project
    context = build_context(
        repository,
        code_map,
        finding_at(SINK_FILE, "cursor.execute(query)"),
        Settings(max_snippet_lines=2),
    )
    assert "more lines" in context.function_source
    assert len(context.function_source.splitlines()) == 3  # 2 kept + the marker


def test_enclosing_function_finds_the_innermost(project):
    _, code_map = project
    symbol = enclosing_function(code_map, SINK_FILE, line_of(SINK_FILE, "cursor.execute(query)"))
    assert symbol.name == "search_users_by_name"
