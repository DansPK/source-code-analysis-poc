"""MCP server over Streamable HTTP, and the `scan-mcp` entry point.

The third thin adapter, beside the CLI and `app/api/`: it exposes `run_scan()` and the
ask agent as MCP tools for the VS Code extension, and adds nothing to the pipeline.
Errors are not caught here -- the SDK turns a raised exception into an error result.
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

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


@server.tool()
def scan(path: str) -> ScanReport:
    """Scan a folder or a single file for security vulnerabilities and return the full
    report. `path` must be absolute. A scan runs Semgrep and an LLM call per finding,
    so it can take several minutes."""
    return run_scan(None, path, get_settings())


@server.tool()
def ask(path: str, question: str, transcript: list[str] | None = None) -> dict[str, Any]:
    """Answer a question about the code in the project folder at `path` (absolute).
    To ask a follow-up, pass back the `transcript` returned by the previous answer."""
    settings = get_settings()
    repository = load_source(None, path, settings)
    code_map = analyze(repository)
    answer, transcript = ask_agent(
        get_client(settings), repository, code_map, question,
        transcript=transcript, max_steps=settings.max_ask_steps,
    )
    return {"answer": answer, "transcript": transcript}


def main() -> None:
    logger.info("MCP server on http://%s:%d/mcp", settings.api_host, settings.mcp_port)
    server.run(transport="streamable-http")
