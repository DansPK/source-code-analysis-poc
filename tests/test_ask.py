"""The ask agent: tool dispatch, and not answering beyond what it read."""

import pytest

from app.agent.ask import MAX_STEPS, ask
from app.agent.tools import find_symbol, read_file, search
from app.config.settings import Settings
from app.repository.analyzer import analyze
from app.source.loader import load_source

SAMPLE = "tests/vulnerable_samples/flask_app"


@pytest.fixture(scope="module")
def project():
    repository = load_source(None, SAMPLE, Settings())
    return repository, analyze(repository)


class ScriptedClient:
    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def complete_json(self, system, user):
        self.prompts.append(user)
        return self.replies.pop(0) if self.replies else {"answer": "done"}


# --- tools ---------------------------------------------------------------------


def test_read_file_numbers_lines(project):
    repository, _ = project
    out = read_file(repository, path="routes/search.py", start=1, end=3)
    assert out.splitlines()[0].startswith("    1  ")


def test_read_file_reports_a_bad_path(project):
    repository, _ = project
    assert "Cannot read" in read_file(repository, path="nope.py")


def test_search_finds_the_source(project):
    repository, _ = project
    assert "routes/search.py" in search(repository, pattern=r"request\.args")


def test_search_rejects_a_bad_pattern(project):
    repository, _ = project
    assert "Invalid pattern" in search(repository, pattern="(unclosed")


def test_find_symbol_reports_definition_and_callers(project):
    repository, code_map = project
    out = find_symbol(repository, code_map, name="search_users_by_name")
    assert "defined: database/user_repository.py" in out
    assert "called in: services/search_service.py" in out


def test_find_symbol_says_when_there_is_nothing(project):
    repository, code_map = project
    assert "No symbol" in find_symbol(repository, code_map, name="does_not_exist")


# --- loop ----------------------------------------------------------------------


def test_tool_result_is_fed_back_before_answering(project):
    repository, code_map = project
    client = ScriptedClient(
        {"tool": "find_symbol", "args": {"name": "search_users_by_name"}},
        {"answer": "It is defined in the repository layer."},
    )

    answer, transcript = ask(client, repository, code_map, "Where is it defined?")

    assert answer == "It is defined in the repository layer."
    assert "database/user_repository.py" in client.prompts[1]  # the tool output came back
    assert len(transcript) == 3  # question, tool result, answer


def test_unknown_tool_is_corrected_not_fatal(project):
    repository, code_map = project
    client = ScriptedClient({"tool": "rm_rf", "args": {}}, {"answer": "ok"})

    assert ask(client, repository, code_map, "q")[0] == "ok"
    assert "no tool named" in client.prompts[1]


def test_step_limit_is_enforced(project):
    repository, code_map = project
    client = ScriptedClient(*[{"tool": "list_files", "args": {}}] * (MAX_STEPS + 2))

    answer, _ = ask(client, repository, code_map, "q")

    assert "ran out of steps" in answer
    assert len(client.prompts) == MAX_STEPS


def test_transcript_continues_a_conversation(project):
    repository, code_map = project
    client = ScriptedClient({"answer": "first"}, {"answer": "second"})

    _, transcript = ask(client, repository, code_map, "one")
    _, transcript = ask(client, repository, code_map, "two", transcript)

    assert "QUESTION: one" in client.prompts[1]  # earlier turn still visible
