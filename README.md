# AI Source Code Vulnerability Scanner

A proof of concept for combining static analysis with an LLM to find and explain
vulnerabilities in a source project.

Static analysis reports *where* suspicious code is, not whether it matters. A
`cursor.execute()` built by string concatenation looks identical whether the value came
from an HTTP request or a constant, and the scanner usually cannot tell, because the answer
is in another file. Handing the whole repository to an LLM instead is expensive, does not
scale, and gives the model no way to know which lines deserve attention.

This project tests the middle path: a scanner decides **what is suspicious**, the project's
own structure supplies **the code that explains it**, and the LLM only decides **whether it
is real**. The LLM never searches for vulnerabilities.

## How it works

```
Git URL or local path
  → Source manager        clone or resolve to a project root
  → Repository analyzer   detect language/framework, build a code map (one AST pass per file)
  → Semgrep               candidate findings
  → Finding parser        normalize to a scanner-independent Finding
  → Context investigator  walk the call chain from the finding back to an entry point
  → AI analyzer           is this real? where does the input come from?
  → Validator             reject claims not grounded in this codebase
  → Agent                 explain it, recommend a fix
  → Report                terminal or JSON
```

The bundled fixture spreads one vulnerability across three files:

```python
# routes/search.py
q = request.args["q"]                   # attacker-controlled
results = search_users(q)
# services/search_service.py            forwards it unchanged
# database/user_repository.py
query = "SELECT ... LIKE '%" + name + "%'"
cursor.execute(query)                   # Semgrep reports only this line
```

Semgrep reports the last line. On its own that is not judgeable — `name` could be anything.
The context investigator walks the call chain backwards, finds `request.args["q"]` two files
away, and sends the model the three functions involved (~1.3 KB) instead of the repository.

Two design rules keep it honest: **the validator only lowers a verdict** — a file the model
names that the project does not contain, or a claim with no evidence, is downgraded to
`Needs Manual Review` rather than dropped or trusted — and **the agent recommends, it never
patches**.

Full design: [`AI_Source_Code_Vulnerability_Scanner_POC.md`](AI_Source_Code_Vulnerability_Scanner_POC.md).

## Setup

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and an API key for any
OpenAI-compatible endpoint. Semgrep installs as a Python dependency.

```bash
uv sync
cp .env.example .env
```

```ini
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=sk-...
LLM_MODEL=deepseek-chat
```

Other settings, all optional: `MAX_CALLER_DEPTH` and `MAX_CALLEE_DEPTH` (default `2`) control
how many levels of context are gathered, `MAX_SNIPPET_LINES` (`40`) truncates each excerpt,
`SEMGREP_RULES` (`rules/semgrep`) and `TEMP_DIR` (`temp`) set paths, `API_HOST`/`API_PORT`
bind the server. Raising the depths increases prompt size and cost.

## Usage

```bash
uv run scan --path /path/to/project           # local directory
uv run scan --path app/services/user.py       # single file
uv run scan --repo https://github.com/stamparm/DSVW

uv run scan --path <dir> --format json        # writes reports/scan-<timestamp>.json
uv run scan --path <dir> --out /tmp/reports   # chosen directory
```

`--format json` replaces the terminal output; pass `--out` alone to get both.

HTTP API — same report, synchronous, minutes on a large repo:

```bash
uv run scan-api      # http://localhost:8000, OpenAPI docs at /docs
curl -X POST localhost:8000/scan -H 'content-type: application/json' \
     -d '{"path": "/path/to/project"}'
```

## Output

```
VULN-001  SQL Injection
Status:      Likely Vulnerable
Severity:    High          Confidence: High

Source:      request.args["q"]  (routes/search.py)
Sink:        cursor.execute()   (database/user_repository.py:17)

Data flow:
    routes/search.py
  → services/search_service.py
  → database/user_repository.py

What happens:    [why the flow is dangerous]
Suggested fix:   [what to change, and in which layer]
```

Statuses are `Likely Vulnerable`, `Possible Vulnerability`, `Likely False Positive` and
`Needs Manual Review`; confidence is `High`, `Medium` or `Low`. These are a model's
assessment, not a guarantee. The JSON report adds the gathered context, so a finding can be
re-examined without re-running the scan.

## Project structure

Each package under `app/` is one pipeline stage, exchanging the shared types in `models/`.

```
app/
├── main.py       CLI, and run_scan() -- where the pipeline is wired together
├── models/       shared data types; plain Pydantic, no logic
├── source/       clone a Git URL or resolve a local path
├── repository/   file discovery, language detection, code map
├── scanners/     run Semgrep
├── findings/     normalize scanner output, drop duplicates
├── context/      callers, callees, cross-file flow
├── ai/           prompts, LLM client, analyzer, validator
├── agent/        explanation and fix recommendation
├── report/       terminal and JSON output
└── api/          FastAPI wrapper over run_scan()

rules/semgrep/              detection rules
tests/vulnerable_samples/   intentionally vulnerable apps used as ground truth
```

## Development

```bash
uv run pytest                                    # full suite
uv run pytest tests/test_context.py::test_name   # one test
```

The LLM is stubbed at the client boundary in tests, so the suite needs no API key and makes
no network calls. Conventions are in [`AGENTS.md`](AGENTS.md); current state and known
pitfalls in [`HANDOFF.md`](HANDOFF.md).

## Limitations

The pipeline is complete; its coverage is not.

- **One vulnerability class.** A single rule, for SQL injection reaching `execute()`,
  `executemany()`, `objects.raw()` or `objects.extra()`. A clean result means no SQL
  injection of a matched shape — not a safe project.
- **Python only.** Other languages are listed but not parsed, so no cross-file context.
- **Name-based symbol resolution.** No type inference or scope analysis; call sites are
  found by searching source text, so a name in a comment can misattribute a caller. The cost
  is irrelevant context, not a wrong verdict.
- **Three LLM calls per finding**, roughly 10–20 seconds each.
- **Accuracy is unmeasured.** Correct on the projects below, but with no systematic
  ground-truth evaluation and no established false-positive rate.

Out of scope by design: dynamic testing, exploitation, whole-program taint analysis,
dependency and secret scanning, automatic patching, CI/CD integration.

## Tested against

| Project | Files | Findings |
|---|---|---|
| [stamparm/DSVW](https://github.com/stamparm/DSVW) | 12 | 3 |
| [adeyosemanputra/pygoat](https://github.com/adeyosemanputra/pygoat) | 276 | 2 |
| [we45/Vulnerable-Flask-App](https://github.com/we45/Vulnerable-Flask-App) | 19 | 1 |
| [anxolerd/dvpwa](https://github.com/anxolerd/dvpwa) | 58 | 1 |
| [nVisium/django.nV](https://github.com/nVisium/django.nV) | 190 | 1 |

All were assessed `Likely Vulnerable` at high confidence. These projects contain many more
vulnerabilities than that; the counts reflect the single rule currently shipped.
