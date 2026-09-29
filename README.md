# AI Source Code Vulnerability Scanner (POC)

Scans a whole source project for vulnerabilities by combining static analysis with AI
reasoning. Semgrep finds suspicious code, the scanner gathers cross-file context around each
finding, an LLM judges whether it is really exploitable, and an agent explains it in plain
language with a suggested fix.

The design is specified in [`AI_Source_Code_Vulnerability_Scanner_POC.md`](AI_Source_Code_Vulnerability_Scanner_POC.md).
Working on this repo — human or AI — starts at [`HANDOFF.md`](HANDOFF.md) and [`AGENTS.md`](AGENTS.md).

## Pipeline

```
Source (Git URL | local path)
  → Repository Analyzer → Code Map
  → Semgrep → candidate findings
  → Cross-file Context Investigator
  → AI Analyzer → Validator
  → AI Agent (explanation + suggested fix)
  → CLI / JSON report
```

Semgrep decides what is *suspicious*; the LLM only decides what is *real*. The whole
repository is never handed to the model.

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env
```

`LLM_MOCK=1` in `.env` runs the entire pipeline against canned responses, so no API key is
needed to try it. For real analysis set `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` to any
OpenAI-compatible provider.

## Run

```bash
# Local project or single file
uv run scan --path tests/vulnerable_samples/flask_app --mock

# Git repository
uv run scan --repo https://github.com/example/vulnerable-app --mock

# JSON report
uv run scan --path <dir> --format json --out reports/
```

HTTP API (same pipeline behind FastAPI):

```bash
uv run scan-api                      # http://localhost:8000, docs at /docs
curl -X POST localhost:8000/scan -H 'content-type: application/json' \
     -d '{"path":"tests/vulnerable_samples/flask_app","mock":true}'
```

## Tests

```bash
uv run pytest                        # everything
uv run pytest tests/test_context.py  # one file
uv run pytest tests/test_context.py::test_cross_file_chain   # one test
```

`tests/vulnerable_samples/` holds intentionally vulnerable applications used as ground truth.
They are fixtures — never run them.

## Status

POC under construction, built in milestones. `HANDOFF.md` states which milestone is current,
what is already working, and what is frozen.
