# HANDOFF

Living state file for whichever agent picks this repo up next. **Read this before anything
else.** Rewrite the Status / Done / In progress sections as the last act of your session;
append to Gotchas, never rewrite it.

Working rule: **finish one milestone completely, run its verification command, update this
file, then stop.** Do not start the next milestone in the same session.

## Status

- **All milestones complete (M0–M8).** The POC pipeline works end to end.
- Last updated: 2026-09-29 by Claude Opus 5 (Claude Code)

## Done

- **M0 — Scaffold and ground-truth fixture.** Package tree under `app/`, dependencies in
  `pyproject.toml` (`uv sync` clean), `Settings` in `app/config/settings.py`, `get_logger()`
  in `app/utils/logging.py`, CLI skeleton in `app/main.py`, and the vulnerable Flask fixture
  at `tests/vulnerable_samples/flask_app/`.
  Verified: `uv sync && uv run scan --help`; `uv run semgrep --version` → 1.178.0.
- **M1 — Frozen data contracts.** `app/models/` complete, re-exported from `app.models`.
  `Finding` (spec §5.5), `Repository`/`SourceFile`/`Symbol`/`FileNode`/`CodeMap` (§5.2–5.3),
  `CodeExcerpt`/`FindingContext`/`AIAnalysis`/`ReportItem`/`ScanReport` (§7–§13).
  **Plain data only — no methods, no properties, no unused fields.** Verified:
  `uv run pytest` → 9 passed.
- **M2 — Source manager.** `load_source(repo, path, settings)` in `app/source/loader.py` is
  the convergence point: Git and local input both return a `Repository` with a directory
  `root`. Shallow clone into `Settings.temp_dir`, replacing any previous clone. Failures raise
  `SourceError` (CLI exit 2). Verified: `uv run pytest` → 18 passed, including a real clone of
  a repo the test creates on disk; `uv run scan --repo https://github.com/octocat/Hello-World.git`.

## Evaluation against a real model (2026-09-29)

First runs with a real key (DeepSeek `deepseek-flash`, OpenAI-compatible endpoint).

**On the fixture:** Likely Vulnerable / High / High, ~11s, 3 LLM calls (analysis,
explanation, remediation). The analysis was better than the canned one: it cited line
numbers, noticed the docstring saying VULNERABLE, and recommended parameterization at the
driver boundary *because* manual escaping handles LIKE wildcards badly.

**On third-party code it had never seen** (`github.com/we45/Vulnerable-Flask-App`, 19 files):
found the real SQL injection at `app/app.py:265`, correctly identified the source as
`request.json['search']`, reconstructed the flow, and reasoned that exploitation requires a
valid JWT because the endpoint is authenticated. ~18s end to end.

**One bug this exposed, now fixed:** the validator downgraded a correct analysis because the
model answered `routes/search.py:11 (q = request.args["q"])` instead of a bare path. The
mock could never have caught it — the canned replies were written by the same hand as the
validator, so they agreed with it by construction. **Treat mock-only agreement as unproven.**

**Rule coverage is the real limit, not the architecture.** On that same project:

| Rules | Findings |
|---|---|
| ours (`rules/semgrep/`, 1 rule) | 1 — the SQL injection |
| `p/security-audit` (registry) | 10 — none of them the SQL injection |

The registry ruleset *missed* the `%`-interpolation SQLi that our taint rule caught, and
found 10 issues ours cannot see (cert validation, template injection, deserialization).
Running both configs together is roughly a one-line change in `semgrep_scanner.scan()` and is
the single highest-value improvement available.

## In progress

Nothing mid-flight. **The POC is feature-complete** — every stage in the spec works, from a
Git URL or local path through to a natural-language report with a suggested fix.

There is no next milestone. Work from here is a choice, not a plan. The most valuable
directions, roughly in order:

1. **More Semgrep rules.** `rules/semgrep/` holds one rule (SQL injection). Command
   injection, path traversal and unsafe deserialization are the obvious next ones, and each
   needs a matching fixture and a canned reply in `tests/fixtures/mock_responses.json`.
2. **A real-LLM evaluation run** (spec §20). Everything so far is verified against canned
   replies. Point it at a deliberately vulnerable project (OWASP Juice Shop, DVWA) with a real
   key and measure how often the AI's verdict matches the known ground truth.
3. **A second language.** The code map is Python-only via stdlib `ast`; a tree-sitter backend
   behind the same `CodeMap` types would cover JavaScript without touching `context/`.
4. **Background scans for the API.** `POST /scan` blocks for minutes on a real repository.

## Frozen contracts

**`app/models/` is frozen as of M1.** Import from `app.models`, not the submodules — that
package's `__all__` is the contract surface. Changing a field means updating every consumer;
keep this list current as consumers appear.

- `Finding` — produced by `findings/parser.py` (M4), consumed by everything after it.
- `Repository` — `root`/`origin`/`single_file` set by `source/loader.py` (M2); the rest filled
  by `repository/analyzer.py` (M3). `CodeMap`, `FileNode`, `Symbol` — produced by M3, consumed
  by `context/` (M5).
- `SourceError` (`app/source/__init__.py`) — the one exception the CLI turns into exit code 2.
  Its message is shown to the user verbatim, so keep messages actionable.
- `FindingContext` — produced by `context/builder.py` (M5), rendered into a prompt by
  `ai/prompts.py` (M6).
- `AIAnalysis` — **this is the LLM's output schema.** Its `Literal` enums are what stop a
  hallucinated verdict from reaching the report. Validator (M6) may only downgrade.
- `ReportItem`, `ScanReport` — produced by `agent/` + `report/` (M7), serialized by the API (M8).
- `Settings` (`app/config/settings.py`) — treat field *names* as stable; modules receive a
  `Settings` instance rather than reading the environment.
- `run_scan()` in `app/main.py` — the single pipeline entry point. The CLI (M7) and the
  FastAPI layer (M8) are both thin adapters over it; no pipeline logic may live in either.

## Gotchas

- `folder-structure.md` lists both `findings/model.py` and `models/finding.py`. **Only
  `app/models/` exists** — all Pydantic models live there; `app/findings/` holds just
  `parser.py` and `deduplicator.py`. Do not recreate `findings/model.py`.
- `folder-structure.md` predates the decision to add a FastAPI layer, so it does not show
  `app/api/` (M8). The directory exists and is empty apart from `__init__.py`.
- The fixture app's package layout (`routes/`, `services/`, `database/`) uses plain relative
  imports with no top-level package, matching the spec's example. The code map resolves
  symbols by name, so this is fine — but do not "fix" the fixture's imports; tests assert
  against its current shape.
- `find_user_by_id()` in the fixture is a *safe* parameterized query kept as a false-positive
  control. The pipeline must not report it as Likely Vulnerable.
- `pytest` is configured with `norecursedirs = tests/vulnerable_samples` so the fixture app is
  never collected as tests.
- Semgrep is installed as a Python package, so it is `uv run semgrep`, not a system binary.
  `SemgrepScanner.is_available()` (M4) must check accordingly.
- All `file` fields on models are **relative to the repository root**; only `Repository.root`
  is absolute. Keep it that way or reports and code-map lookups stop agreeing on paths.
- `AIAnalysis.model_json_schema()` produces the exact §9 field list — M6 should embed that in
  the system prompt rather than hand-writing the schema, so the two can never drift.
- `app.routes` on this FastAPI version holds an `_IncludedRouter` wrapper rather than the
  flattened routes, so inspecting it looks like `include_router()` did nothing. It did — check
  with a request or `/openapi.json`, not by reading `app.routes`.
- The API deliberately has no job store: `POST /scan` runs the scan synchronously in
  FastAPI's threadpool. Fine for a demo, not for a real repository.
- **The mock LLM client was removed.** There is no `--mock` flag, no `LLM_MOCK` setting and
  no canned-response file: every scan calls a real model. Tests stay offline by stubbing at
  the client boundary — `monkeypatch.setattr("app.main.get_client", lambda s: StubClient())`.
  Keep new tests doing the same; the suite must never need a key or the network.
- `ReportItem.id` (`VULN-001`) is the user-facing id and is assigned by the agent;
  `Finding.id` (`F-001`) is the scanner's internal one. They are deliberately separate — after
  deduplication the F-numbers have gaps, which would look like missing findings in a report.
- **Everything written goes to `workspace/`** in the checkout (`settings.WORKSPACE`): clones
  in `projects/`, reports in `reports/`, `ask` conversations in `sessions/`. Nothing may be
  written outside the checkout, into the user's home, or into the project being examined.
  Semgrep rules ship in `app/rules/semgrep/`, resolved from `PACKAGE_ROOT`.
- The tool was briefly installed system-wide with `uv tool install`; that was reverted, and
  the project is run with `uv run` from the checkout. Do not install it without asking.
- **Configured paths resolve against the project, not the cwd** (`settings.project_path()`).
  The scanner is pointed at other people's code, so it is routinely run from elsewhere;
  `rules/semgrep`, `temp/` and the mock responses all broke when run from `/tmp` before this.
  There is a regression test.
- The prompt's schema is generated from `AIAnalysis.model_fields` and `get_args()` on the
  `Literal` enums, so it cannot drift from what actually validates. A test asserts every field
  name appears in the prompt. (Simpler than embedding `model_json_schema()`, which is verbose.)
- **The analyzer grounds the model's answer**: `data_flow`, `source_file` and `sink_file` are
  filled from the context when the model omits them, because our own analysis is the
  trustworthy source for those. A model-supplied value is left alone — and then checked by the
  validator against the real file list.
- `MockClient` matches canned replies by looking for the vulnerability type in the prompt text.
  Add new ones to `tests/fixtures/mock_responses.json`; anything unmatched returns the
  `default` entry, which is `Needs Manual Review`.
- **Semgrep needs the skip list passed explicitly.** Because `--no-git-ignore
  --x-ignore-semgrepignore-files` also discards `.gitignore`, Semgrep happily scanned `.venv`
  and reported 9 findings from site-packages. It is now given `--exclude` for every entry in
  `file_filter.SKIP_DIRS`, which keeps the analyzer and the scanner agreeing on what is
  project code. There is a regression test.
- Call sites are located by searching the calling function's **source text** for the name, not
  by a second AST pass, because the code map stores calls per file rather than per function.
  A name in a comment or string can therefore produce a wrong caller. That costs the model a
  little irrelevant context, never a wrong verdict, and it avoids re-parsing every file.
- `trace_to_entry_point()` prefers a caller that is a known entry point when several files call
  the same name. Without that, a common helper name walks the chain into whichever file sorts
  first.
- **Semgrep's defaults silently hide findings.** It scans only git-tracked files and applies a
  built-in ignore list that excludes `tests/`. Scanning the fixture returned *zero* results
  until `--no-git-ignore --x-ignore-semgrepignore-files` were added. The second flag is
  experimental (`--x-`), so if a Semgrep upgrade drops it, the fixture tests fail loudly —
  that is deliberate, and the fix is to find its replacement, not to move the fixture.
- **Semgrep's `extra.lines` is the literal string "requires login"** in the OSS engine, so the
  code snippet is read from disk by the parser. Never trust that field.
- `check_id` comes back namespaced by the rules path (`rules.semgrep.python-sqli-concat`).
  Kept as-is in `Finding.rule_id` because it is the scanner's real id; reports should lead with
  `vulnerability_type` instead.
- **No `base_scanner.py` ABC exists**, though `folder-structure.md` lists one. An abstract base
  with a single implementation is the over-engineering AGENTS.md forbids, and it would not earn
  its keep: scanner independence is already provided by `findings/parser.py`, which is where
  the scanner's output shape stops mattering. Add the ABC when a second scanner actually
  arrives and there is something to share.
- Semgrep call names are stored **unqualified**: `cursor.execute(...)` is recorded as
  `execute`, not `cursor.execute`. M5 matches on that, so a common method name can collide
  across files — combine it with the import list rather than trusting it alone.
- `analyze()` mutates the `Repository` it is given and returns only the `CodeMap`. Deliberate:
  the caller already holds the repository, so returning both would just be noise.
- Scanning this project itself reports `frameworks=['flask']` — correct, because
  `tests/vulnerable_samples/flask_app` really is part of the tree. Not a bug.
- `Repository.single_file` was added to the frozen models in M2: spec §17 requires single-file
  input, and a file's root is its parent directory. M3 is its consumer — it must not be ignored,
  or `scan --path some_file.py` silently scans the whole directory.
- GitPython wraps git's stderr as `\n  stderr: '...'`; `git_loader` unwraps it to the `fatal:`
  line so users see one clean sentence. Don't pass `exc.stderr` through raw.
- `CodeMap.symbol_index` maps a name to a *list* of files: resolution is by name only, so two
  files defining `search()` both come back. M5 must handle ambiguity, not assume one hit.
- The models are deliberately **data only**. Lookup logic (enclosing function, callers of a
  symbol) belongs in M5's `symbol_resolver.py` and `call_graph.py`, which exist for exactly
  that. An earlier pass put those helpers on the models; they were removed. Do not put them
  back — logic on the contract makes the contract hard to freeze.

## Next milestones

- **M2** — Source manager: local + Git loaders converging on one pipeline entry.
- **M3** — Repository analyzer and `ast`-based code map (Python only).
- **M4** — Semgrep scanner, finding parser (the Semgrep isolation boundary), deduplicator.
- **M5** — Cross-file context investigator, bounded by `Settings` depths. The core feature.
- **M6** — AI analyzer + validator, with `MockClient` so tests need no API key.
- **M7** — Agent (explain + recommend) and report engine; wire `run_scan()`.
- **M8** — FastAPI layer over `run_scan()`.

Full detail for each is in the approved plan:
`~/.claude/plans/ai-source-code-vulnerability-scanner-po-scalable-whale.md`.
