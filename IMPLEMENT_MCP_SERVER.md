# Implement: MCP server for source-code-analysis-poc

This file explains what to build and why. It has no code on purpose.
Claude Code should read it, then read `AGENTS.md` and `HANDOFF.md`, then implement.

## Goal

Add an MCP server to this repo.
A VS Code extension will start the server and talk to it.
The server lets the extension do two things:

1. Scan a folder or a file for vulnerabilities.
2. Ask a question about the code in a folder.

The server adds nothing new to the pipeline.
It is only a new way to reach what already exists.

## Treat it as milestone M9

Follow the working rhythm in `AGENTS.md`.

- Do this as one milestone: **M9 — MCP server**.
- Finish it, run the tests, update `HANDOFF.md`, and commit.
- Commit subject: `M9: MCP server over stdio for scan and ask`.
- Do not start other work in the same session.

## Where it fits

The repo already has two thin adapters over the pipeline:

- The CLI in `app/main.py`.
- The HTTP API in `app/api/`.

The MCP server is the third adapter.
It must stay just as thin.
No pipeline logic goes inside it.

- For scanning, it calls `run_scan()` in `app/main.py`.
- For questions, it calls the existing `ask()` function in `app/agent/ask.py`.
  It loads the source and builds the code map first, the same way `app/ask.py` does.

## Transport

Use the **stdio** transport.

- The extension starts the server as a child process.
- They talk over stdin and stdout.
- No network port is needed.

**Important rule: nothing else may write to stdout.**
Stdout carries the protocol. One stray `print` breaks the connection.

- The pipeline already logs to stderr through `app/utils/logging.py`. Keep it that way.
- The only `print` calls today are in the CLI entry points. The server must not call those.
- The extension will read stderr and show it as live progress. So good log lines help the user.

## Dependency

Use the official MCP Python SDK (package name `mcp`).
Its `FastMCP` helper is enough. Do not write the protocol by hand.

- Add it with `uv add mcp`.
- This is the only new dependency.

## Entry point

Add one new script in `pyproject.toml`: `scan-mcp`.
It starts the server on stdio.

The extension will start it like this (a concept, not code):
run `uv run --directory <path to this repo> scan-mcp`.

Using `--directory` matters.
It makes uv use this repo's environment and `.env`, even when VS Code has a different folder open.

Put the server in a single module, for example `app/mcp_server.py`.
Avoid naming a package `mcp` inside `app/`, so no one confuses it with the SDK.

## Tools to expose

Keep it to two tools. Add more only when the extension needs them.

### Tool 1: `scan`

- **Input:** `path` — an absolute path to a folder or a single file.
- **What it does:** runs the full pipeline through `run_scan()`.
- **Output:** the full `ScanReport` as JSON. This is the same shape the HTTP API returns.
- **Description for the model/client:** say that it scans for security issues, and that it can take several minutes.

A single file works already. `load_local()` handles files. So "scan this file" needs no extra code.

### Tool 2: `ask`

- **Input:**
  - `path` — the project folder.
  - `question` — the user's question.
  - `transcript` — optional. The transcript from the last answer.
- **What it does:** runs the existing ask agent.
- **Output:** an object with `answer` and `transcript`.

Why return the transcript?
The chat UI wants follow-up questions.
The server stays stateless. The client keeps the transcript and sends it back next time.
This matches how `ask()` already works.

## Errors

Do not add broad `try/except`.

- If a tool raises, the MCP SDK turns it into an error result with the message.
- `SourceError`, `ScannerError` and `AIError` already have clear messages. Let them pass through.
- A bad path should give an error result like "Path does not exist". It must not crash the server.

## Long-running scans

A scan can take minutes. This is normal.

- The server does not need to do anything special.
- The client must set a long timeout. That is the extension's job (see the other file).
- Keep the tools synchronous, as `AGENTS.md` asks. The server handles one client, so blocking is fine.

## Where files are written

No change. Everything still goes to `workspace/` in this repo.
The server must never write into the project being scanned.

## Tests

Add `tests/test_mcp.py`. Test the behaviour, not the SDK.

Stub the LLM at the client boundary, the same way `tests/test_api.py` does.
Stub both places that call `get_client`: `app.main` and the new server module.

Use the SDK's in-memory client session. It connects a client to the server with no subprocess.

Tests to write:

1. The server lists exactly two tools: `scan` and `ask`.
2. `scan` on `tests/vulnerable_samples/flask_app` returns the report. The SQL injection item is "Likely Vulnerable". This proves it matches the CLI.
3. `ask` returns the stubbed answer, and the transcript starts with the question.
4. `scan` on a path that does not exist returns an error result, not a crash.

All tests must pass with no API key and no network, as the rest of the suite does.

## Docs to update

- `README.md`: add a short "MCP server" section. Say how to start it, and name the two tools.
- `AGENTS.md`: in the Environment block, add the `uv run scan-mcp` command. In Architecture, say the MCP server is a third thin adapter over `run_scan()`.
- `HANDOFF.md`: record M9 as done, how it was verified, and this gotcha: "stdout belongs to the protocol; never print in the server path."

## How to check it by hand

1. Run `uv sync`.
2. Use the MCP Inspector to connect to `uv run --directory <repo> scan-mcp`.
3. Call `scan` with the absolute path of the Flask sample.
4. Check the report comes back, and the logs show on stderr.

## Keep it small

This milestone should be small. A rough guide:

- The server module: about 40–60 lines.
- The test file: about 60–80 lines.

If it grows much bigger, something is being over-built. Re-read "Keep it simple" in `AGENTS.md`.
