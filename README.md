# AI Source Code Vulnerability Scanner

A proof of concept that combines static analysis with an LLM to find and explain
vulnerabilities in a source project.

## Overview

Static analysis reports where suspicious code is, not whether it matters. A
`cursor.execute()` built by string concatenation looks the same whether the value came from
an HTTP request or from a constant. The scanner usually cannot tell the difference, because
the answer is in another file. Passing the whole repository to an LLM instead is expensive,
does not scale, and gives the model no way to know which lines deserve attention.

This project splits the work. Semgrep decides what is suspicious. The project's call graph
supplies the code that explains it. The LLM decides only whether the finding is real, and
writes the explanation for the developer. The LLM is never asked to search for
vulnerabilities.

The full design is in
[`AI_Source_Code_Vulnerability_Scanner_POC.md`](AI_Source_Code_Vulnerability_Scanner_POC.md).

## How it works

```
Git URL or local path
  -> Source manager        clone or resolve to a project root
  -> Repository analyzer   detect language and framework, build a code map
  -> Semgrep               candidate findings
  -> Finding parser        normalize to a scanner-independent Finding
  -> Context investigator  walk the call chain from the finding to an entry point
  -> AI analyzer           decide whether the finding is real
  -> Validator             reject claims not grounded in this codebase
  -> Agent                 explain the finding, recommend a fix
  -> Report                terminal or JSON
```

The bundled test fixture spreads one vulnerability across three files:

```python
# routes/search.py
q = request.args["q"]                   # attacker-controlled
results = search_users(q)

# services/search_service.py            forwards the value unchanged

# database/user_repository.py
query = "SELECT ... LIKE '%" + name + "%'"
cursor.execute(query)                   # Semgrep reports only this line
```

Semgrep reports the last line. That line alone is not enough to reach a verdict, since
`name` could be anything. The context investigator walks the call chain backwards, finds
`request.args["q"]` two files away, and sends the model the three functions involved, about
1.3 KB, rather than the repository.

Two rules constrain what reaches the report. The validator can only lower a verdict: if the
model names a file the project does not contain, or gives a verdict without evidence, the
finding is downgraded to `Needs Manual Review` rather than dropped or trusted. The agent
recommends changes and never modifies code.

## Requirements

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/)
- An API key for an OpenAI-compatible LLM endpoint

Semgrep is installed as a Python dependency.

## Installation

```bash
uv sync
cp .env.example .env
```

Set the model configuration in `.env`:

```ini
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=sk-...
LLM_MODEL=deepseek-chat
```

Everything the tool writes goes to `workspace/` inside the checkout: cloned repositories in
`workspace/projects/`, JSON reports in `workspace/reports/`, and saved `ask` conversations in
`workspace/sessions/`. Nothing is written outside the checkout or into the project being
examined.

Optional settings: `MAX_CALLER_DEPTH` and `MAX_CALLEE_DEPTH` (default `2`) set how many
levels of callers and callees are gathered, `MAX_SNIPPET_LINES` (`40`) truncates each code
excerpt, `SEMGREP_RULES` and `TEMP_DIR` set paths, and
`API_HOST` and `API_PORT` bind the server. Higher depth values increase prompt size and cost.

## Usage

```bash
uv run scan --path workspace/projects/DSVW
uv run scan --path /path/to/project
uv run scan --path app/services/user.py       # single file
uv run scan --repo https://github.com/stamparm/DSVW   # clones into workspace/projects/

uv run scan --path <dir> --format json        # writes workspace/reports/scan-<timestamp>.json
uv run scan --path <dir> --out /tmp/reports   # writes to a chosen directory
```

`--format json` replaces the terminal output. Pass `--out` on its own to get both.

The HTTP API returns the same report. Scans run synchronously and can take several minutes
on a large repository.

```bash
uv run scan-api      # http://localhost:8000, OpenAPI docs at /docs

curl -X POST localhost:8000/scan -H 'content-type: application/json' \
     -d '{"path": "/path/to/project"}'
```

### Asking questions

`ask` answers questions about a project instead of scanning it. The model explores the code
one step at a time using four tools (list files, read a file, regex search, find a symbol's
definition and callers) and answers from what it read.

```bash
uv run ask --path <dir> "where does user input reach the database?"
uv run ask --path <dir>                       # interactive terminal UI
```

Without a question it opens a terminal UI with tool calls shown as they run, markdown
answers, and two kinds of persistent history: arrow-key recall of past input, and saved
conversations kept per project under `workspace/sessions/`. Commands are `/help`, `/clear`, `/sessions`,
`/resume [name]`, `/history`, `/files` and `/exit`.

## Output

```
VULN-001  SQL Injection
Status:      Likely Vulnerable
Severity:    High          Confidence: High

Source:      request.args["q"]  (routes/search.py)
Sink:        cursor.execute()   (database/user_repository.py:17)

Data flow:
    routes/search.py
  -> services/search_service.py
  -> database/user_repository.py

What happens:    [why the flow is dangerous]
Suggested fix:   [what to change, and in which layer]
```

Statuses are `Likely Vulnerable`, `Possible Vulnerability`, `Likely False Positive` and
`Needs Manual Review`. Confidence is `High`, `Medium` or `Low`. Both are the model's
assessment and are not guarantees.

The JSON report contains the same fields plus the gathered context, so a finding can be
reviewed without running the scan again.

## Project structure

Each package under `app/` is one pipeline stage. Stages exchange the shared types defined in
`app/models/`.

```
app/
├── main.py       scan CLI, and run_scan(), where the pipeline is wired together
├── ask.py        ask CLI
├── tui.py        terminal UI for ask
├── models/       shared data types; plain Pydantic, no logic
├── source/       clone a Git URL or resolve a local path
├── repository/   file discovery, language detection, code map
├── scanners/     run Semgrep
├── findings/     normalize scanner output, remove duplicates
├── context/      callers, callees, cross-file flow
├── ai/           prompts, LLM client, analyzer, validator
├── agent/        explanation, fix recommendation, and the ask agent
├── report/       terminal and JSON output
└── api/          FastAPI wrapper over run_scan()

app/rules/semgrep/          detection rules, shipped with the package
tests/vulnerable_samples/   intentionally vulnerable applications used as ground truth
workspace/                  everything the tool writes: clones, reports, conversations
```

## Development

```bash
uv run pytest                                    # full suite
uv run pytest tests/test_context.py::test_name   # a single test
```

Tests replace the LLM client with a stub, so the suite requires no API key and makes no
network calls.

Conventions are documented in [`AGENTS.md`](AGENTS.md). Current state and known pitfalls are
in [`HANDOFF.md`](HANDOFF.md).

## Limitations

The pipeline is complete. Its detection coverage is not.

- One vulnerability class. A single rule covers SQL injection reaching `execute()`,
  `executemany()`, `objects.raw()` or `objects.extra()`. A result with no findings means no
  SQL injection of a matched shape was found, not that the project is secure.
- Python only. Other languages are listed in the report but not parsed, so no cross-file
  context is built for them.
- Symbol resolution is name-based, without type inference or scope analysis. Call sites are
  located by searching function source text, so a name in a comment can produce an incorrect
  caller. The result is irrelevant context rather than an incorrect verdict.
- Each finding costs three LLM calls and takes about 10 to 20 seconds.
- Accuracy has not been measured. Results were correct on the projects listed below, but
  there has been no systematic evaluation against known ground truth and no false-positive
  rate has been established.

Out of scope by design: dynamic testing, exploitation, whole-program taint analysis,
dependency and secret scanning, automatic patching, and CI/CD integration.

## License

[MIT](LICENSE)

## Tested against

| Project | Files | Findings |
|---|---|---|
| [stamparm/DSVW](https://github.com/stamparm/DSVW) | 12 | 3 |
| [adeyosemanputra/pygoat](https://github.com/adeyosemanputra/pygoat) | 276 | 2 |
| [we45/Vulnerable-Flask-App](https://github.com/we45/Vulnerable-Flask-App) | 19 | 1 |
| [anxolerd/dvpwa](https://github.com/anxolerd/dvpwa) | 58 | 1 |
| [nVisium/django.nV](https://github.com/nVisium/django.nV) | 190 | 1 |

Every reported finding was assessed `Likely Vulnerable` with high confidence. These projects
contain more vulnerabilities than these counts show; the counts reflect the single rule
currently shipped.
