# HANDOFF

Living state file for whichever agent picks this repo up next. **Read this before anything
else.** Rewrite the Status / Done / In progress sections as the last act of your session;
append to Gotchas, never rewrite it.

Working rule: **finish one milestone completely, run its verification command, update this
file, then stop.** Do not start the next milestone in the same session.

## Status

- **Current milestone: M2 — Source manager** (not started)
- Last updated: 2026-09-29 by Claude Opus 5 (Claude Code)

## Done

- **M0 — Scaffold and ground-truth fixture.** Package tree under `app/`, dependencies in
  `pyproject.toml` (`uv sync` clean), `Settings` in `app/config/settings.py`, `get_logger()`
  in `app/utils/logging.py`, CLI skeleton in `app/main.py`, and the vulnerable Flask fixture
  at `tests/vulnerable_samples/flask_app/`.
  Verified: `uv sync && uv run scan --help`; `uv run semgrep --version` → 1.178.0.
- **M1 — Frozen data contracts.** `app/models/` complete and re-exported from
  `app.models` (18 names). `Finding` (spec §5.5), `Repository`/`SourceFile`/`Symbol`/
  `FileNode`/`CodeMap` (§5.2–5.3), `CodeExcerpt`/`FindingContext`/`AIAnalysis`/`ReportItem`/
  `ScanReport` (§7–§13). Verified: `uv run pytest` → 24 passed.

## In progress

Nothing mid-flight. M1 finished cleanly.

**Next concrete step:** M2 source manager — `app/source/local_loader.py`,
`git_loader.py`, `loader.py`. `load_source()` returns a populated-enough `Repository`
(at minimum `root`, and `origin` when cloned) for both input kinds; file discovery itself
belongs to M3, so do not build it here. Clone shallow into `Settings.temp_dir`. Then wire
`--path`/`--repo` in `main.py` far enough to print the resolved root.

## Frozen contracts

**`app/models/` is frozen as of M1.** Import from `app.models`, not the submodules — that
package's `__all__` is the contract surface. Changing a field means updating every consumer;
keep this list current as consumers appear.

- `Finding` — produced by `findings/parser.py` (M4), consumed by everything after it.
- `Repository`, `CodeMap`, `FileNode`, `Symbol` — produced by `repository/analyzer.py` (M3),
  consumed by `context/` (M5).
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
- `CodeMap.defining_files()` returns a *list*: symbol resolution is by name only, so two files
  defining `search()` both come back. Callers must handle ambiguity, not assume one hit.
- `CodeMap.callers_of()` already excludes a file that calls a symbol it also defines; don't
  re-filter that in M5.

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
