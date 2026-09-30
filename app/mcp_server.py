"""MCP server over Streamable HTTP, and the `scan-mcp` entry point.

The third thin adapter, beside the CLI and `app/api/`: it exposes `run_scan()` and the
ask agent as MCP tools for the VS Code extension, and adds nothing to the pipeline.
Errors are not caught here -- the SDK turns a raised exception into an error result.

The tools stream while they run: each finding of a scan, each step and piece of the
answer of an ask, and the pipeline's log lines, are sent as MCP progress notifications
whose `message` is one JSON event. The pipeline stays synchronous; it runs in a worker
thread so the event loop is free to send those notifications. A client that asks for no
progress gets none.

A client names its code in one of three ways: `path` (a directory this server can read),
`repo` + `branch` (cloned here), or `archive` (a base64 zip it uploads). `subpath` narrows
a clone or an archive to one folder or file.
"""

import hmac
import json
import logging
import re
import threading
from collections.abc import Callable
from typing import Any

import anyio
import uvicorn
from mcp.server.fastmcp import Context, FastMCP
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.agent.ask import ask as ask_agent
from app.ai.client import get_client
from app.config.settings import get_settings
from app.main import run_scan
from app.models import ScanReport
from app.repository.analyzer import analyze
from app.source import SourceError
from app.source.loader import load_source
from app.utils.logging import get_logger

logger = get_logger(__name__)

settings = get_settings()
# Stateless: the client keeps the ask transcript and sends it back, so there is no
# session for the server to track.
server = FastMCP(
    "source-code-vuln-poc", host=settings.mcp_host, port=settings.mcp_port, stateless_http=True
)

# Git URLs a client may ask us to clone. Not file:// or a bare path: those would read
# this server's own disk under the guise of a repository.
REMOTE_URL = re.compile(r"^(https://|ssh://|git@)")


def _source(
    path: str | None, repo: str | None, branch: str | None, archive: str | None, subpath: str | None
) -> dict[str, Any]:
    """Check the client named its code exactly one way, and return load_source() kwargs."""
    if sum(bool(x) for x in (path, repo, archive)) != 1:
        raise SourceError("Give exactly one of `path`, `repo` or `archive`.")
    if repo and not REMOTE_URL.match(repo):
        raise SourceError(f"Only https://, ssh:// and git@ repository URLs are accepted, not {repo}")
    return {"repo": repo, "path": path, "branch": branch, "archive": archive, "subpath": subpath}


class _LogForwarder(logging.Handler):
    """Forward one request's pipeline log lines to its client, which cannot see our stderr.

    Created in the request's worker thread, it only passes on records from that thread,
    so two requests running at once do not see each other's logs.
    """

    def __init__(self, send_event: Callable[[dict], None]):
        super().__init__(logging.INFO)
        self.send_event = send_event
        self.thread = threading.get_ident()

    def emit(self, record: logging.LogRecord) -> None:
        if record.thread == self.thread:
            self.send_event({"type": "log", "text": record.getMessage()})


async def _stream(ctx: Context, work: Callable[[Callable[[dict], None]], Any]) -> Any:
    """Run `work(emit)` in a worker thread; everything it emits, and its logs, stream out."""
    sent = 0

    def emit(event: dict) -> None:
        nonlocal sent
        sent += 1  # progress must increase with every notification
        anyio.from_thread.run(ctx.report_progress, sent, None, json.dumps(event))

    def in_thread() -> Any:
        forwarder = _LogForwarder(emit)
        logging.getLogger("app").addHandler(forwarder)
        try:
            return work(emit)
        finally:
            logging.getLogger("app").removeHandler(forwarder)

    return await anyio.to_thread.run_sync(in_thread)


@server.tool()
async def scan(
    ctx: Context,
    path: str | None = None,
    repo: str | None = None,
    branch: str | None = None,
    archive: str | None = None,
    subpath: str | None = None,
) -> ScanReport:
    """Scan code for security vulnerabilities and return the full report. Name the code
    with exactly one of: `path` (absolute, on this server), `repo` (Git URL, optionally
    with `branch`) or `archive` (base64 zip); `subpath` narrows a repo or archive to one
    folder or file. A scan runs Semgrep and an LLM call per finding, so it can take
    several minutes. Streams `{"type": "finding", "total", "item"}` as each finding is
    judged and `{"type": "log", "text"}` for pipeline progress."""
    source = _source(path, repo, branch, archive, subpath)

    def work(emit: Callable[[dict], None]) -> ScanReport:
        def on_item(item, total):
            emit({"type": "finding", "total": total, "item": item.model_dump(mode="json")})

        return run_scan(
            source["repo"], source["path"], get_settings(), on_item=on_item,
            branch=branch, archive=archive, subpath=subpath,
        )

    return await _stream(ctx, work)


@server.tool()
async def ask(
    ctx: Context,
    question: str,
    path: str | None = None,
    repo: str | None = None,
    branch: str | None = None,
    archive: str | None = None,
    transcript: list[str] | None = None,
) -> dict[str, Any]:
    """Answer a question about a project, named like `scan` names it (`path`, `repo` +
    `branch`, or `archive`). To ask a follow-up, pass back the `transcript` returned by
    the previous answer. Streams `{"type": "step", "tool", "args", "why"}` for each tool
    the agent uses and `{"type": "token", "text"}` for each piece of the answer."""
    source = _source(path, repo, branch, archive, None)

    def work(emit: Callable[[dict], None]) -> dict[str, Any]:
        settings = get_settings()
        repository = load_source(settings=settings, **source)
        code_map = analyze(repository)
        answer, new_transcript = ask_agent(
            get_client(settings), repository, code_map, question,
            transcript=transcript, max_steps=settings.max_ask_steps,
            on_step=lambda tool, args, why: emit({"type": "step", "tool": tool, "args": args, "why": why}),
            on_token=lambda text: emit({"type": "token", "text": text}),
        )
        return {"answer": answer, "transcript": new_transcript}

    return await _stream(ctx, work)


def require_api_key(app: ASGIApp, key: str) -> ASGIApp:
    """Refuse every HTTP request that does not carry `Authorization: Bearer <key>`.

    Plain ASGI rather than Starlette middleware: BaseHTTPMiddleware buffers responses,
    which would hold back the streamed events.
    """
    expected = f"Bearer {key}".encode()

    async def guarded(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            given = dict(scope["headers"]).get(b"authorization", b"")
            if not hmac.compare_digest(given, expected):
                response = JSONResponse(
                    {"error": "Missing or invalid API key."},
                    status_code=401, headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
        await app(scope, receive, send)

    return guarded


def main() -> None:
    app = server.streamable_http_app()
    if settings.mcp_api_key:
        app = require_api_key(app, settings.mcp_api_key)
    else:
        logger.warning("MCP_API_KEY is not set: the MCP server accepts requests from anyone who can reach it")
    logger.info("MCP server on http://%s:%d/mcp", settings.mcp_host, settings.mcp_port)
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)
