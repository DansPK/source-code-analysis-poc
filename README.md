# AI Source Code Vulnerability Scanner

A proof of concept for combining static analysis with an LLM to find and explain
vulnerabilities in a source project.

Static analysis tools report where suspicious code is, but not whether it matters. A
`cursor.execute()` built by string concatenation is a finding whether the value came from
an HTTP request or a hardcoded constant, and the tool usually cannot tell the difference
because the answer lives in a different file. This produces alert volumes that teams stop
reading.

Handing the whole repository to an LLM and asking it to find bugs does not solve that. It
is expensive, it does not scale past a small project, and the model has no reliable way to
know which of the thousands of lines it was given deserve attention.

This project tests a middle path:

> Use a deterministic scanner to decide **what is suspicious**. Use the project's own
> structure to gather **the code that explains it**. Use the LLM only to decide **whether it
> is real**, and to explain it to the developer.

The LLM never searches for vulnerabilities. It answers a narrow question about a specific
finding, with the relevant cross-file context supplied to it.

## Purpose

This is a proof of concept, not a product. It exists to answer a few specific questions:

- Can a lightweight code map connect a finding to the code that explains it, without
  compiler-grade analysis?
- Is that context enough for an LLM to judge reachability and exploitability?
- Can the result be presented so a developer knows what to do?
- Does the pipeline stay honest when the model is wrong?

The full design, including what is deliberately out of scope, is in
[`AI_Source_Code_Vulnerability_Scanner_POC.md`](AI_Source_Code_Vulnerability_Scanner_POC.md).

## How it works

```
Git URL or local path
        ↓
  Source manager          clone or resolve, converge on one project root
        ↓
  Repository analyzer     walk the tree, detect language and framework,
        ↓                 build a code map with one AST pass per file
  Semgrep                 candidate findings from pattern and taint rules
        ↓
  Finding parser          normalize to a scanner-independent Finding
        ↓
  Context investigator    walk the call chain from the finding back to an entry point
        ↓
  AI analyzer             is this real? where does the input come from?
        ↓
  Validator               reject claims not grounded in this codebase
        ↓
  Agent                   explain it, recommend a fix
        ↓
  Report                  terminal or JSON
```

### A worked example

The bundled fixture (`tests/vulnerable_samples/flask_app`) spreads one vulnerability across
three files, which is what makes it representative:

```python
# routes/search.py
q = request.args["q"]                   # attacker-controlled
results = search_users(q)

# services/search_service.py
def search_users(query):
    return search_users_by_name(query)  # forwarded unchanged

# database/user_repository.py
query = "SELECT ... WHERE name LIKE '%" + name + "%'"
cursor.execute(query)                   # Semgrep reports only this line
```

Semgrep reports line 17 of `user_repository.py`. On its own that is not enough to judge:
`name` could be anything. The context investigator walks the call chain backwards, finds
`request.args["q"]` two files away, and sends the model the three functions involved —
about 1.3 KB — rather than the repository.

The model returns a structured verdict (status, severity, confidence, source, sink, data
flow, evidence, impact), which the validator checks before anything is reported.

### Why the stages are separate

Each stage does one job and hands on a plain data structure:

- **Semgrep decides what is suspicious.** The LLM is never asked to find vulnerabilities,
  only to judge ones already found.
- **`findings/parser.py` is where Semgrep stops existing.** Everything downstream consumes a
  normalized `Finding`, so a second scanner means a second parser and no other changes.
- **Context is bounded** to the affected function plus one or two levels of callers and
  callees. This is what keeps the prompt small enough to be affordable and focused.
- **The validator only ever lowers a verdict.** If the model names a file the project does
  not contain, or claims a vulnerability without evidence, the finding is downgraded to
  `Needs Manual Review` rather than dropped or trusted.
- **The agent recommends, it does not patch.** Automatic code modification is out of scope.

## Requirements

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/)
- An API key for any OpenAI-compatible LLM endpoint

Semgrep is installed as a Python dependency, so no separate installation is needed.

## Installation

```bash
uv sync
cp .env.example .env
```

Edit `.env`:

```ini
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=sk-...
LLM_MODEL=deepseek-chat
```

Any OpenAI-compatible provider works. A key is required: every scan calls the model.

## Usage

Scan a local project, a single file, or a Git repository:

```bash
uv run scan --path /path/to/project
uv run scan --path app/services/user.py
uv run scan --repo https://github.com/stamparm/DSVW
```

Write a JSON report instead of printing one:

```bash
uv run scan --path <dir> --format json          # writes reports/scan-<timestamp>.json
uv run scan --path <dir> --out /tmp/reports     # writes to a chosen directory
```

`--format json` replaces the terminal output. To get both, pass `--out` and keep the default
format.

### HTTP API

```bash
uv run scan-api      # http://localhost:8000, OpenAPI docs at /docs
```

```bash
curl -X POST localhost:8000/scan \
     -H 'content-type: application/json' \
     -d '{"path": "/path/to/project"}'
```

`POST /scan` returns the same report the CLI produces. Scans run synchronously and can take
minutes on a large repository.

### Configuration

All settings can be set in `.env` or the environment.

| Setting | Default | Meaning |
|---|---|---|
| `LLM_BASE_URL` | OpenAI | Any OpenAI-compatible endpoint |
| `LLM_API_KEY` | — | Required |
| `LLM_MODEL` | `gpt-4o-mini` | Model name |
| `MAX_CALLER_DEPTH` | `2` | Levels of callers gathered as context |
| `MAX_CALLEE_DEPTH` | `2` | Levels of callees gathered as context |
| `MAX_SNIPPET_LINES` | `40` | Truncation limit for each code excerpt |
| `SEMGREP_RULES` | `rules/semgrep` | Rule directory passed to Semgrep |
| `TEMP_DIR` | `temp` | Where Git clones are written |
| `API_HOST`, `API_PORT` | `127.0.0.1:8000` | Bind address for `scan-api` |

Raising the depth limits increases prompt size and cost.

## Output

Terminal output, abbreviated:

```
Scanned 9 files in /path/to/project
1 candidate finding(s) from the scanner → 1 Likely Vulnerable

========================================================================
VULN-001  SQL Injection
========================================================================
Status:      Likely Vulnerable
Severity:    High          Confidence: High

Source:      request.args["q"]  (routes/search.py)
Sink:        cursor.execute()   (database/user_repository.py:17)

Data flow:
    routes/search.py
  → services/search_service.py
  → database/user_repository.py

What happens:
  [two paragraphs explaining the flow and what an attacker could do]

Suggested fix:
  [a specific recommendation, naming the layer it belongs in]
```

The JSON report contains the same information plus the gathered context, so a finding can
be re-examined without re-running the scan.

### Statuses

| Status | Meaning |
|---|---|
| `Likely Vulnerable` | The model found a plausible path from untrusted input to the sink |
| `Possible Vulnerability` | A path exists but something about it is unclear |
| `Likely False Positive` | The pattern matched but the model found a reason it is safe |
| `Needs Manual Review` | No usable verdict, or the verdict failed validation |

Confidence is `High`, `Medium` or `Low`. These are a model's assessment, not a guarantee.

## Project structure

Each package under `app/` is one stage of the pipeline.

```
app/
├── main.py         CLI, and run_scan() -- where the pipeline is wired together
├── models/         shared data types; plain Pydantic, no logic
├── source/         clone a Git URL or resolve a local path
├── repository/     file discovery, language detection, code map
├── scanners/       run Semgrep, return raw output
├── findings/       normalize scanner output, drop duplicates
├── context/        gather callers, callees and the cross-file flow
├── ai/             prompts, LLM client, analyzer, validator
├── agent/          explanation and fix recommendation
├── report/         terminal and JSON output
├── api/            FastAPI wrapper over run_scan()
├── config/         settings
└── utils/          logging

rules/semgrep/              detection rules
tests/vulnerable_samples/   intentionally vulnerable apps used as ground truth
temp/                       cloned repositories
reports/                    generated JSON reports
```

## Development

```bash
uv run pytest                                    # full suite
uv run pytest tests/test_context.py              # one file
uv run pytest tests/test_context.py::test_name   # one test
```

The LLM is stubbed at the client boundary in tests, so the suite needs no API key and makes
no network calls.

Contributors, human or AI, should read [`AGENTS.md`](AGENTS.md) for the working conventions
and [`HANDOFF.md`](HANDOFF.md) for current state and known pitfalls.

## Limitations

This is a proof of concept. The pipeline is complete, but its coverage is not.

**One vulnerability class.** `rules/semgrep/` contains a single rule, for SQL injection
reaching `execute()`, `executemany()`, `objects.raw()` or `objects.extra()`. Command
injection, path traversal, XSS, unsafe deserialization and weak cryptography are not
detected. A clean result means no SQL injection of a shape the rule matches — not that the
project is free of vulnerabilities.

**Python only.** Other languages are listed in the report but not parsed, so no code map or
cross-file context is built for them.

**Name-based symbol resolution.** The code map matches calls by name, with no type
inference or scope analysis. Two functions with the same name in different files are
ambiguous, and call sites are located by searching the calling function's source text, so a
name inside a comment can produce a misattributed caller. The cost is some irrelevant
context, not a wrong verdict.

**Cost and speed.** Each finding costs three LLM calls (analysis, explanation, fix) and
takes roughly 10-20 seconds. A repository with many findings takes proportionally longer.

**Accuracy is not yet measured.** The pipeline has been run against several deliberately
vulnerable projects and produced correct results on each, but no systematic evaluation
against known ground truth has been done, and no false-positive rate has been established.

Also out of scope by design: dynamic testing, exploitation, full taint analysis across the
whole program, dependency and secret scanning, automatic patching, and CI/CD integration.

## Tested against

| Project | Files | Findings |
|---|---|---|
| [stamparm/DSVW](https://github.com/stamparm/DSVW) | 12 | 3 |
| [adeyosemanputra/pygoat](https://github.com/adeyosemanputra/pygoat) | 276 | 2 |
| [we45/Vulnerable-Flask-App](https://github.com/we45/Vulnerable-Flask-App) | 19 | 1 |
| [anxolerd/dvpwa](https://github.com/anxolerd/dvpwa) | 58 | 1 |
| [nVisium/django.nV](https://github.com/nVisium/django.nV) | 190 | 1 |

Each reported finding was assessed `Likely Vulnerable` at high confidence by the model.
These projects contain many vulnerabilities beyond those counts; the numbers reflect the
single rule currently shipped, not the projects' actual vulnerability count.
