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

## Project structure

Each package under `app/` is one stage of that pipeline, in the order shown above. A stage
takes and returns the shared types in `app/models/` and knows nothing about its neighbours'
internals, which is what lets the stages be built and tested independently.

```
app/
├── main.py         CLI, and run_scan() -- the one place the pipeline is wired together
├── models/         shared data contracts; plain Pydantic types, no logic
├── source/         input: clone a Git URL or resolve a local path to a project root
├── repository/     walk the project, detect languages, build the whole-project code map
├── scanners/       run static analysis (Semgrep) and return its raw output
├── findings/       normalize scanner output into Finding, and drop duplicates
├── context/        gather the code around a finding -- callers, callees, cross-file flow
├── ai/             ask the LLM whether a finding is real, and validate what it answers
├── agent/          turn a validated finding into an explanation and a suggested fix
├── report/         render the result as CLI text or JSON
├── api/            FastAPI wrapper over run_scan()
├── config/         settings from .env
└── utils/          logging
```

Two boundaries carry most of the design:

- **`findings/parser.py`** is where Semgrep stops existing. It converts Semgrep's JSON into
  `Finding`, and nothing after it knows which scanner produced the result — so adding a second
  scanner means writing another parser, not touching the pipeline.
- **`context/`** is the feature that makes the AI useful. A scanner reports the line where a
  dangerous call happens; this package walks outward to find where the data came from, which is
  usually a different file. Bounded to a couple of levels of callers and callees, deliberately —
  the model should receive a flow, not a repository.

Supporting directories:

```
tests/vulnerable_samples/   intentionally vulnerable apps used as ground truth (never run them)
rules/semgrep/              custom Semgrep rules, so a demo doesn't depend on the registry
temp/                       cloned repositories
reports/                    generated JSON reports
```

`HANDOFF.md` says which of these are implemented so far.

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
