"""M9: the MCP server. Like the HTTP layer, it must add nothing but transport."""

import json
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from app.mcp_server import server

SAMPLE = str(Path("tests/vulnerable_samples/flask_app").resolve())

STUB_REPLY = {
    "vulnerability_type": "SQL Injection",
    "status": "Likely Vulnerable",
    "severity": "High",
    "confidence": "High",
    "evidence": "Concatenated with no parameterization.",
    "protection_found": "None.",
    "impact": "Rows readable.",
    "explanation": "The request value reaches the query unchanged.",
    "suggested_fix": "Use a parameterized query.",
    # The ask agent reads only this field; the scan pipeline ignores it.
    "answer": "The search route builds SQL by concatenation.",
}


class StubClient:
    def complete_json(self, system, user):
        return STUB_REPLY


@pytest.fixture(autouse=True)
def stub_llm(monkeypatch):
    """The LLM is stubbed at the client boundary, in both places that create one."""
    monkeypatch.setattr("app.main.get_client", lambda settings: StubClient())
    monkeypatch.setattr("app.mcp_server.get_client", lambda settings: StubClient())


async def call(tool, **arguments):
    async with create_connected_server_and_client_session(server) as session:
        return await session.call_tool(tool, arguments)


async def test_exactly_two_tools_are_exposed():
    async with create_connected_server_and_client_session(server) as session:
        tools = (await session.list_tools()).tools
    assert {t.name for t in tools} == {"scan", "ask"}


async def test_scan_returns_the_same_report_the_cli_produces():
    result = await call("scan", path=SAMPLE)

    assert not result.isError
    item = next(
        i for i in result.structuredContent["items"]
        if i["finding"]["rule_id"].endswith("python-sqli-concat")
    )
    assert item["analysis"]["status"] == "Likely Vulnerable"


async def test_ask_returns_the_answer_and_a_transcript_to_send_back():
    result = await call("ask", path=SAMPLE, question="Where is user input used in SQL?")

    assert not result.isError
    assert result.structuredContent["answer"] == STUB_REPLY["answer"]
    assert result.structuredContent["transcript"][0] == (
        "QUESTION: Where is user input used in SQL?"
    )


async def test_bad_path_is_an_error_result_not_a_crash():
    result = await call("scan", path="/no/such/place")

    assert result.isError
    assert "does not exist" in result.content[0].text


class StreamingStubClient(StubClient):
    """Streams its reply in small pieces, as the real client does."""

    def stream_json(self, system, user):
        text = json.dumps({"answer": STUB_REPLY["answer"]})
        for start in range(0, len(text), 7):
            yield text[start : start + 7]


async def call_streaming(tool, **arguments):
    """Call a tool asking for progress, and collect the events it streams."""
    events = []

    async def on_progress(progress, total, message):
        events.append(json.loads(message))

    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool(tool, arguments, progress_callback=on_progress)
    return result, events


async def test_context_is_not_a_tool_argument():
    async with create_connected_server_and_client_session(server) as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
    assert set(tools["scan"].inputSchema["properties"]) == {"path"}
    assert set(tools["ask"].inputSchema["properties"]) == {"path", "question", "transcript"}


async def test_scan_streams_each_finding_before_the_report():
    result, events = await call_streaming("scan", path=SAMPLE)

    assert [e["type"] for e in events] == ["finding"] * result.structuredContent["candidates_found"]
    assert events[0]["total"] == result.structuredContent["candidates_found"]
    streamed = {e["item"]["id"] for e in events}
    assert streamed == {i["id"] for i in result.structuredContent["items"]}


async def test_ask_streams_the_answer_as_it_is_written(monkeypatch):
    monkeypatch.setattr("app.mcp_server.get_client", lambda settings: StreamingStubClient())

    result, events = await call_streaming("ask", path=SAMPLE, question="Where is SQL built?")

    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert len(tokens) > 1
    assert "".join(tokens) == result.structuredContent["answer"]
