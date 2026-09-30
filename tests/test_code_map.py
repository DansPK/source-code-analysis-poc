"""M3: the project map that later cross-file investigation walks."""

from pathlib import Path

import pytest

from app.config.settings import Settings
from app.repository.analyzer import analyze
from app.repository.file_filter import iter_files
from app.source.loader import load_source

SAMPLE = "tests/vulnerable_samples/flask_app"


@pytest.fixture
def analyzed():
    repository = load_source(None, SAMPLE, Settings())
    return repository, analyze(repository)


def test_detects_python_and_flask(analyzed):
    repository, _ = analyzed
    assert repository.languages == ["python"]
    assert repository.frameworks == ["flask"]


def test_routes_file_is_an_entry_point(analyzed):
    """Where attacker-controlled input enters -- M5 walks back to here."""
    repository, _ = analyzed
    assert "routes/search.py" in repository.entry_points


def test_symbol_resolves_to_its_defining_file(analyzed):
    """The link that makes cross-file investigation possible."""
    _, code_map = analyzed
    assert code_map.symbol_index["search_users"] == ["services/search_service.py"]
    assert code_map.symbol_index["search_users_by_name"] == ["database/user_repository.py"]


def test_service_layer_calls_the_database_layer(analyzed):
    _, code_map = analyzed
    assert "search_users_by_name" in code_map.files["services/search_service.py"].calls
    assert "execute" in code_map.files["database/user_repository.py"].calls


def test_function_line_ranges_cover_the_vulnerable_sink(analyzed):
    """M5 maps a finding's line number back to its function using these ranges."""
    _, code_map = analyzed
    node = code_map.files["database/user_repository.py"]
    sink = next(f for f in node.functions if f.name == "search_users_by_name")
    source = Path(SAMPLE, "database/user_repository.py").read_text().splitlines()
    vulnerable_line = next(
        i for i, line in enumerate(source, 1) if "cursor.execute(query)" in line
    )
    assert sink.line <= vulnerable_line <= sink.end_line


def test_single_file_input_analyzes_only_that_file():
    repository = load_source(None, f"{SAMPLE}/routes/search.py", Settings())
    analyze(repository)
    assert [f.path for f in repository.files] == ["search.py"]


def test_noise_directories_are_skipped(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    for junk in ("node_modules", ".git", "__pycache__"):
        (tmp_path / junk).mkdir()
        (tmp_path / junk / "junk.py").write_text("x = 1\n")
    assert [p.name for p in iter_files(tmp_path)] == ["app.py"]


def test_unparseable_file_is_mapped_as_far_as_possible(tmp_path):
    """tree-sitter recovers from syntax errors: a broken file is not fatal, and the
    parts that do parse still reach the map."""
    (tmp_path / "broken.py").write_text("def oops(:\n    pass\n\ndef later():\n    run()\n")
    (tmp_path / "fine.py").write_text("def ok():\n    pass\n")
    repository = load_source(None, str(tmp_path), Settings())

    code_map = analyze(repository)

    assert "ok" in code_map.symbol_index
    assert code_map.symbol_index["later"] == ["broken.py"]
