# AI Source Code Vulnerability Scanner

A proof of concept that combines static analysis with an LLM to find and explain
vulnerabilities in a source project.

> **Use it from VS Code:** [Nokran](https://github.com/DansPK/nokran-poc) is a chat extension
> that talks to this project's MCP server. See [Trying it with Nokran](#trying-it-with-nokran).

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
- Network access, for Semgrep's registry rulesets

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
excerpt, `MAX_ASK_STEPS` (`20`) limits how many tool calls the ask agent may make, `SEMGREP_CONFIGS` is a comma-separated list of Semgrep rulesets (registry packs such as
`p/security-audit`, or local directories), `TEMP_DIR` sets where clones land, and
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

### MCP server

`scan-mcp` serves the same pipeline over MCP (Streamable HTTP), for editor integrations such
as the VS Code extension. It exposes two tools: `scan` (a folder or file path, returns the full
report) and `ask` (a project path and a question; pass back the returned `transcript` for a
follow-up).

```bash
uv run scan-mcp                               # http://127.0.0.1:8001/mcp (MCP_PORT to change)
uv run --directory /path/to/this/repo scan-mcp   # from anywhere, using this repo's .venv and .env
```

A client names the code in one of three ways, so the server does not have to share a disk
with it:

| Argument | Meaning |
| --- | --- |
| `path` | An absolute folder or file path **on the server**. |
| `repo` (+ `branch`) | A Git URL the server clones (`https://`, `ssh://` or `git@` only). |
| `archive` | A base64 zip of the project, uploaded by the client (at most `MAX_UPLOAD_MB`, default 100). |

`subpath` narrows a clone or an archive to one folder or file. Clones and uploads land in
`workspace/projects/` (uploads under `uploads/<hash>`, reused when the same archive is sent again).

Set `MCP_API_KEY` in `.env` and every request must carry `Authorization: Bearer <key>`;
without it the server warns at startup and accepts anyone who can reach it. To serve other
machines set `MCP_HOST=0.0.0.0` — and then always set `MCP_API_KEY`. Logs go to stderr, and are
also streamed to the client (below).

Both tools stream while they run, as MCP progress notifications whose `message` is one JSON
event. A client that sends a progress token (in the TypeScript SDK, by passing `onprogress`)
receives:

| Tool | Event |
| --- | --- |
| `scan` | `{"type": "analysis", "number", "total", "finding", "analysis"}` when a finding's verdict is in |
| `scan` | `{"type": "finding_text", "number", "field", "text"}` as its `explanation` and `suggested_fix` are written |
| `scan` | `{"type": "finding", "number", "total", "item": <report item>}` when the finding is complete |
| `ask` | `{"type": "step", "tool", "args", "why"}` as the agent uses a tool |
| `ask` | `{"type": "token", "text"}` for each piece of the answer as the model writes it |
| both | `{"type": "log", "level", "text"}` for each pipeline log line, for clients that cannot see stderr |

The final result is the same with or without streaming; a client that asks for no progress
gets none.

### Trying it with Nokran

[Nokran](https://github.com/DansPK/nokran-poc) is the VS Code extension built for this server.
It gives you a chat panel where you can scan a folder or file, ask questions, and watch the
findings and answers stream in. To test the two together:

1. Start this server with an API key:
   ```bash
   uv sync
   echo "MCP_API_KEY=$(openssl rand -hex 32)" >> .env   # plus LLM_API_KEY, see Installation
   uv run scan-mcp
   ```
2. Build and install Nokran:
   ```bash
   git clone https://github.com/DansPK/nokran-poc.git
   cd nokran-poc
   npm install
   npm run package
   code --install-extension nokran-*.vsix
   ```
3. In VS Code settings, search for **Nokran** and paste the `MCP_API_KEY` value into
   **Api Key**. Leave **Mcp Base Url** at `http://127.0.0.1:8001/mcp` and **Source Mode** at
   `path`.
4. Open `tests/vulnerable_samples/flask_app` (or `spring_app`, `express_app`) from this repo,
   click the Nokran icon, and type `scan this code for me`. You should see a SQL injection
   marked **Likely Vulnerable**, with its explanation and fix written out live.
5. Ask a follow-up, for example `where does user input reach the database?`.

Nokran's own documentation covers the settings, the `git` and `upload` modes for a server on
another machine, and troubleshooting.

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

- Detection and cross-file analysis are multi-language. Semgrep's registry rulesets
  (`p/security-audit`, `p/default`, `p/owasp-top-ten`, `p/secrets`) cover every language
  Semgrep supports, and our own rules cover string-built SQL in Python, Java and
  JavaScript/TypeScript. The code map (tree-sitter) covers Python, Java, JavaScript,
  TypeScript, Go, PHP, C#, Ruby, Kotlin, Scala, Swift, Rust, C and C++, so findings in those
  languages get callers, callees and a flow chain. Entry points are recognized for the common
  web frameworks of each (Flask/Django/FastAPI, Spring/JAX-RS/servlets, Express/Koa/Fastify/
  NestJS, Gin/Echo/Fiber/net/http, Laravel/Symfony, ASP.NET, Sinatra, Actix/Axum/Rocket, Ktor).
  Anything else (shell, Terraform, YAML workflows) is analyzed with the code around the
  finding alone.
- If the rulesets report nothing, the AI never sees the project: a scan with 0 candidates is
  "no known pattern matched", not "no vulnerabilities". Use `ask` for logic flaws such as
  missing authorization.
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
