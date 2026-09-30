"""MCP server over Streamable HTTP, and the `scan-mcp` entry point.

The third thin adapter, beside the CLI and `app/api/`: it exposes `run_scan()` and the
ask agent as MCP tools for the VS Code extension, and adds nothing to the pipeline.
Errors are not caught here -- the SDK turns a raised exception into an error result.

The tools stream while they run: each finding of a scan, and each step and piece of the
answer of an ask, is sent as an MCP progress notification whose `message` is one JSON
event. The pipeline stays synchronous; it runs in a worker thread so the event loop is
free to send those notifications. A client that asks for no progress gets none.
"""

import json
from collections.abc import Callable
from typing import Any

import anyio
from mcp.server.fastmcp import Context, FastMCP

from app.agent.ask import ask as ask_agent
from app.ai.client import get_client
from app.config.settings import get_settings
from app.main import run_scan
from app.models import ScanReport
from app.repository.analyzer import analyze
from app.source.loader import load_source
from app.utils.logging import get_logger

logger = get_logger(__name__)

settings = get_settings()
# Stateless: the client keeps the ask transcript and sends it back, so there is no
# session for the server to track.
server = FastMCP(
    "source-code-vuln-poc", host=settings.api_host, port=settings.mcp_port, stateless_http=True
)


def _emitter(ctx: Context) -> Callable[[dict], None]:
    """Send an event to the client from the worker thread the pipeline runs in."""
    sent = 0

    def emit(event: dict) -> None:
        nonlocal sent
        sent += 1  # progress must increase with every notification
        anyio.from_thread.run(ctx.report_progress, sent, None, json.dumps(event))

    return emit


@server.tool()
async def scan(path: str, ctx: Context) -> ScanReport:
    """Scan a folder or a single file for security vulnerabilities and return the full
    report. `path` must be absolute. A scan runs Semgrep and an LLM call per finding,
    so it can take several minutes. Each finding is also streamed as a progress event
    `{"type": "finding", "total": <candidates>, "item": <ReportItem>}` once judged."""
    emit = _emitter(ctx)

    def on_item(item, total):
        emit({"type": "finding", "total": total, "item": item.model_dump(mode="json")})

    return await anyio.to_thread.run_sync(
        lambda: run_scan(None, path, get_settings(), on_item=on_item)
    )


@server.tool()
async def ask(
    path: str, question: str, ctx: Context, transcript: list[str] | None = None
) -> dict[str, Any]:
    """Answer a question about the code in the project folder at `path` (absolute).
    To ask a follow-up, pass back the `transcript` returned by the previous answer.
    Streams progress events `{"type": "step", "tool", "args", "why"}` for each tool the
    agent uses and `{"type": "token", "text"}` for each piece of the answer."""
    emit = _emitter(ctx)

    def run() -> dict[str, Any]:
        settings = get_settings()
        repository = load_source(None, path, settings)
        code_map = analyze(repository)
        answer, new_transcript = ask_agent(
            get_client(settings), repository, code_map, question,
            transcript=transcript, max_steps=settings.max_ask_steps,
            on_step=lambda tool, args, why: emit({"type": "step", "tool": tool, "args": args, "why": why}),
            on_token=lambda text: emit({"type": "token", "text": text}),
        )
        return {"answer": answer, "transcript": new_transcript}

    return await anyio.to_thread.run_sync(run)


def main() -> None:
    logger.info("MCP server on http://%s:%d/mcp", settings.api_host, settings.mcp_port)
    server.run(transport="streamable-http")
