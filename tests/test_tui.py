"""The TUI, driven headlessly by Textual's test harness."""

import pytest

from app.config.settings import Settings
from app.repository.analyzer import analyze
from app.source.loader import load_source
from app.tui import AskApp
from app.tui.widgets import (
    CITATION,
    AssistantMessage,
    Citations,
    Notice,
    ToolCall,
    UserMessage,
)

SAMPLE = "tests/vulnerable_samples/flask_app"


class StubClient:
    """Streams a JSON answer in pieces, the way a real client does."""

    def __init__(self, *replies):
        self.replies = list(replies)

    def stream_json(self, system, user):
        reply = self.replies.pop(0) if self.replies else '{"answer": "done"}'
        for i in range(0, len(reply), 7):
            yield reply[i : i + 7]

    def complete_json(self, system, user):
        return {"answer": "done"}


@pytest.fixture
def app():
    settings = Settings()
    repository = load_source(None, SAMPLE, settings)
    code_map = analyze(repository)
    client = StubClient(
        '{"tool": "find_symbol", "args": {"name": "search_users"}, "why": "locate it"}',
        '{"answer": "It is defined in services/search_service.py:6."}',
    )
    return AskApp(client, repository, code_map, settings)


async def test_asking_shows_tool_call_then_streamed_answer(app):
    async with app.run_test() as pilot:
        await pilot.press(*"where is it", "enter")
        await pilot.pause(delay=0.5)

        assert app.query(UserMessage)
        assert app.query(ToolCall), "the tool call should be visible as it runs"
        answer = app.query_one(AssistantMessage)
        assert "services/search_service.py" in answer.text


async def test_answer_citations_become_clickable(app):
    async with app.run_test() as pilot:
        await pilot.press(*"where is it", "enter")
        await pilot.pause(delay=0.5)

        assert app.query(Citations)
        assert app.query_one(AssistantMessage).citations() == [
            ("services/search_service.py", 6)
        ]


async def test_unknown_command_is_reported(app):
    async with app.run_test() as pilot:
        await pilot.press(*"/nope", "enter")
        await pilot.pause()
        assert "Unknown command" in app.query(Notice).last().text


async def test_new_conversation_clears_the_log(app):
    async with app.run_test() as pilot:
        await pilot.press(*"hello", "enter")
        await pilot.pause(delay=0.5)
        app.action_new()
        await pilot.pause()
        assert not app.query(UserMessage)
        assert app.transcript == []


async def test_export_writes_markdown(app, tmp_path, monkeypatch):
    monkeypatch.setattr("app.tui.app.WORKSPACE", tmp_path)
    async with app.run_test() as pilot:
        app.transcript = ["QUESTION: what is this", "ANSWER: a scanner"]
        await pilot.press(*"/export", "enter")
        await pilot.pause()

    written = list(tmp_path.glob("conversation-*.md"))
    assert written and "a scanner" in written[0].read_text()


async def test_file_viewer_opens_on_a_citation(app):
    async with app.run_test() as pilot:
        app.action_open_file("routes/search.py", 11)
        await pilot.pause()
        assert app.screen_stack[-1].path == "routes/search.py"


def test_citation_pattern_ignores_version_numbers():
    assert CITATION.findall("see a.py:12 but not v1.2 or 3.4") == [("a.py", "12")]
