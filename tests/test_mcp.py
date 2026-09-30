"""M9: the MCP server. Like the HTTP layer, it must add nothing but transport."""

import base64
import io
import json
import logging
import zipfile
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from app.mcp_server import require_api_key, server

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
        text = json.dumps(STUB_REPLY)
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
    assert set(tools["scan"].inputSchema["properties"]) == {"path", "repo", "branch", "archive", "subpath"}
    assert set(tools["ask"].inputSchema["properties"]) == {"question", "path", "repo", "branch", "archive", "transcript"}


async def test_scan_streams_each_finding_before_the_report():
    result, events = await call_streaming("scan", path=SAMPLE)

    findings = [e for e in events if e["type"] == "finding"]
    assert len(findings) == result.structuredContent["candidates_found"]
    assert findings[0]["total"] == result.structuredContent["candidates_found"]
    streamed = {e["item"]["id"] for e in findings}
    assert streamed == {i["id"] for i in result.structuredContent["items"]}


async def test_ask_streams_the_answer_as_it_is_written(monkeypatch):
    monkeypatch.setattr("app.mcp_server.get_client", lambda settings: StreamingStubClient())

    result, events = await call_streaming("ask", path=SAMPLE, question="Where is SQL built?")

    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert len(tokens) > 1
    assert "".join(tokens) == result.structuredContent["answer"]


async def test_scan_streams_the_pipeline_log_a_remote_client_cannot_see(caplog):
    caplog.set_level(logging.INFO)  # as app/utils/logging.py configures it outside pytest
    _, events = await call_streaming("scan", path=SAMPLE)

    logs = [e["text"] for e in events if e["type"] == "log"]
    assert any(line.startswith("Running Semgrep") for line in logs)
    assert any(line.startswith("Candidate findings") for line in logs)


async def test_scan_an_uploaded_archive():
    """What a client on another machine does: send the project instead of a path."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for file in Path(SAMPLE).rglob("*.py"):
            zf.write(file, file.relative_to(SAMPLE))
    archive = base64.b64encode(buffer.getvalue()).decode()

    result = await call("scan", archive=archive)

    assert not result.isError
    assert any(i["finding"]["file"] == "database/user_repository.py" for i in result.structuredContent["items"])


@pytest.mark.parametrize(
    "arguments",
    [{}, {"path": SAMPLE, "repo": "https://example.com/x.git"}, {"repo": "file:///etc"}, {"repo": "/etc"}],
)
async def test_source_must_be_named_exactly_once_and_safely(arguments):
    result = await call("scan", **arguments)
    assert result.isError


async def _asgi_status(app, headers):
    """Send one GET through an ASGI app and return the response status."""
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "GET", "path": "/mcp", "headers": headers, "query_string": b""}
    await app(scope, receive, send)
    return sent[0]["status"]


async def test_api_key_is_required_when_configured():
    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    guarded = require_api_key(inner, "s3cret")

    assert await _asgi_status(guarded, []) == 401
    assert await _asgi_status(guarded, [(b"authorization", b"Bearer wrong")]) == 401
    assert await _asgi_status(guarded, [(b"authorization", b"Bearer s3cret")]) == 200


async def test_scan_streams_verdict_then_text_then_item_per_finding(monkeypatch):
    """The card can appear with its verdict, then type out its explanation and fix."""
    monkeypatch.setattr("app.main.get_client", lambda settings: StreamingStubClient())

    result, events = await call_streaming("scan", path=SAMPLE)

    for item in result.structuredContent["items"]:
        number = int(item["id"].removeprefix("VULN-"))
        mine = [e for e in events if e.get("number") == number]
        kinds = [e["type"] for e in mine]
        assert kinds[0] == "analysis" and kinds[-1] == "finding"
        assert mine[0]["analysis"]["status"] == item["analysis"]["status"]
        for field in ("explanation", "suggested_fix"):
            pieces = [e["text"] for e in mine if e["type"] == "finding_text" and e["field"] == field]
            assert len(pieces) > 1
            assert "".join(pieces).strip() == item[field]
