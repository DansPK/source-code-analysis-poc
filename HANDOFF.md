# HANDOFF

Living state file for whichever agent picks this repo up next. **Read this before anything
else.** Rewrite the Status / Done / In progress sections as the last act of your session;
append to Gotchas, never rewrite it.

Working rule: **finish one milestone completely, run its verification command, update this
file, then stop.** Do not start the next milestone in the same session.

## Status

- **Current milestone: M1 — Frozen data contracts** (not started)
- Last updated: 2026-09-29 by Claude Opus 5 (Claude Code)

## Done

- **M0 — Scaffold and ground-truth fixture.** Package tree under `app/`, dependencies in
  `pyproject.toml` (`uv sync` clean), `Settings` in `app/config/settings.py`, `get_logger()`
  in `app/utils/logging.py`, CLI skeleton in `app/main.py`, and the vulnerable Flask fixture
  at `tests/vulnerable_samples/flask_app/`.
  Verified: `uv sync && uv run scan --help`; `uv run semgrep --version` → 1.178.0.

## In progress

Nothing mid-flight. M0 finished cleanly.

**Next concrete step:** write `app/models/finding.py`, `repository.py`, `analysis.py` as
specified in M1 of the plan, plus `tests/test_models.py`. Field lists come from the spec:
§5.5 for `Finding`, §9 for `AIAnalysis`, §10 for the status/confidence enums. Use
`Literal[...]` for those enums so an invalid LLM response fails validation instead of
propagating.

## Frozen contracts

Nothing is frozen yet — **M1 freezes `app/models/`**, and from that point every other module
takes and returns those types. Once M1 lands, changing a model means updating every consumer
listed here; keep that list current.

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

## Next milestones

- **M1** — Frozen data contracts in `app/models/`.
- **M2** — Source manager: local + Git loaders converging on one pipeline entry.
- **M3** — Repository analyzer and `ast`-based code map (Python only).
- **M4** — Semgrep scanner, finding parser (the Semgrep isolation boundary), deduplicator.
- **M5** — Cross-file context investigator, bounded by `Settings` depths. The core feature.
- **M6** — AI analyzer + validator, with `MockClient` so tests need no API key.
- **M7** — Agent (explain + recommend) and report engine; wire `run_scan()`.
- **M8** — FastAPI layer over `run_scan()`.

Full detail for each is in the approved plan:
`~/.claude/plans/ai-source-code-vulnerability-scanner-po-scalable-whale.md`.
