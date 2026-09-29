# HANDOFF

Living state file for whichever agent picks this repo up next. **Read this before anything
else.** Rewrite the Status / Done / In progress sections as the last act of your session;
append to Gotchas, never rewrite it.

Working rule: **finish one milestone completely, run its verification command, update this
file, then stop.** Do not start the next milestone in the same session.

## Status

- **Current milestone: M3 — Repository analyzer and code map** (not started)
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

## In progress

Nothing mid-flight. M2 finished cleanly.

**Next concrete step:** M3 repository analyzer — `file_filter.py`, `language_detector.py`,
`code_map.py`, `analyzer.py`. `analyze(repository)` fills in `files`, `languages`,
`frameworks`, `entry_points` and returns a `CodeMap`. **Honour `Repository.single_file`:**
when set, analyze only that file, not the whole directory. One `ast.NodeVisitor` collecting
imports, def/class line ranges and call names; build `symbol_index` from the definitions.

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
