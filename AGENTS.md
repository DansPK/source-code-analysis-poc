# AGENTS.md

Guidance for AI coding agents working in this repository. This is the canonical
instruction file; `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md` and
`.cursor/rules/` all defer to it. Edit this file, not the pointers.

> **Read `HANDOFF.md` first.** It states which milestone is in progress, what already works,
> what is frozen, and the non-obvious gotchas. This file explains *how* to work here;
> `HANDOFF.md` tells you *where the work currently stands*.

## Working rhythm

The POC is built in milestones (M0–M8) and worked on by many agents across sessions. So:

**Finish one milestone completely → run its verification command → update `HANDOFF.md` →
commit → stop.**
Do not start the next milestone in the same session. Leaving a half-finished milestone with no
note in `HANDOFF.md` is the single most expensive thing you can do to the next agent.

One commit per milestone, subject line `M<n>: <what it does>` — so `git log --oneline` reads as
the milestone history and any milestone can be reviewed or reverted on its own.

## Project state

Under construction. The authoritative references are:

- `AI_Source_Code_Vulnerability_Scanner_POC.md` — the full POC specification. Read the relevant
  section before implementing a stage; field lists and enums come from it verbatim.
- `folder-structure.md` — the package layout. Two known deviations, both recorded in
  `HANDOFF.md`: there is no `findings/model.py` (all models live in `app/models/`), and
  `app/api/` was added for the FastAPI layer.
- `HANDOFF.md` — current milestone and frozen contracts.

## Environment

The `.venv` was created with **uv** (Python 3.11). Use uv for dependency and run commands:

```bash
uv sync                                          # install from pyproject.toml
uv add <pkg>                                     # add a dependency
uv run scan --path <dir> --mock                  # run the CLI pipeline
uv run scan-api                                  # run the FastAPI layer (docs at /docs)
uv run pytest                                    # whole test suite
uv run pytest tests/test_context.py              # one file
uv run pytest tests/test_context.py::test_name   # one test
uv run semgrep --version                         # Semgrep is a Python dep, not a system binary
```

Copy `.env.example` to `.env`. `LLM_MOCK=1` runs the whole pipeline on canned responses with
no API key — keep every test runnable that way. No linter or formatter is configured; if you
add one, declare it in `pyproject.toml` and document the command here.

## Architecture

The pipeline is strictly staged, and the separation of stages is the point of the POC — do not collapse them:

```
Source Manager → Repository Analyzer → Static Scanner (Semgrep)
  → Finding Parser → Context Investigator → AI Analyzer → Validator
  → AI Agent → Report Engine
```

Key invariants that span multiple modules:

- **The LLM is not the detector.** Semgrep produces *candidate* findings; the AI only reasons about whether a candidate is real. Never send the whole repository to the model and ask it to find bugs.
- **`findings/parser.py` is the isolation boundary for Semgrep.** Everything downstream consumes the normalized `Finding` model (`models/finding.py`), so a second scanner can be added by writing a new parser plus a `scanners/base_scanner.py` subclass, with no changes elsewhere.
- **Cross-file context is the core feature.** `context/` must resolve a finding beyond its own file: the source of tainted input and the dangerous sink usually live in different files. The intended chain is entry point → route → service → repository → sink, built from `repository/code_map.py`.
- **Context is bounded, not exhaustive.** Target the affected function plus 1–2 levels of callers and callees plus related imports. This bound exists to keep prompts small; widening it is a design change, not a tuning knob.
- **The AI Analyzer returns structured data**, not prose (`vulnerability_type, status, severity, confidence, source, source_file, sink, sink_file, data_flow, evidence, protection_found, impact`). Prose is generated later, by `agent/`.
- **The Validator preserves uncertainty.** Statuses are `Likely Vulnerable`, `Possible Vulnerability`, `Likely False Positive`, `Needs Manual Review`; confidence is `High`/`Medium`/`Low`. Uncertain analysis must never be reported as confirmed.
- **The Agent recommends, it does not patch.** Automatic code modification is explicitly out of scope for the POC (section 17).
- **`run_scan()` in `app/main.py` is the only pipeline entry point.** The CLI and the FastAPI
  layer (`app/api/`) are thin adapters over it. No pipeline logic belongs in either adapter.
- **The LLM backend is provider-agnostic.** Everything goes through the `LLMClient` protocol in
  `ai/client.py` (OpenAI-compatible `base_url`, or `MockClient`). No module may import a vendor
  SDK directly.

Both Git-URL and local-path inputs must converge on the same internal pipeline after `source/`. Cloned repos go to `temp/`; `reports/` holds generated output; custom Semgrep rules live in `rules/semgrep/`.

## Keep it simple

This is a POC, and over-building it is the most likely way to fail. Each module should be the
simplest thing that demonstrates its stage:

- No plugin systems, registries, DI containers, or async. Straight-line synchronous code.
- One class per module at most; prefer module-level functions.
- Python only, stdlib `ast` for parsing — no tree-sitter.
- Add a dependency only when a milestone calls for it.
- Every module's public surface is a function taking and returning `app/models/` types. That is
  what lets milestones be owned independently.

Out of scope (spec §17): dynamic testing, exploitation, full taint/data-flow analysis, RAG or
vector search, multi-agent orchestration, auto-patching, CI/CD integration, web UI. If a stage
feels like it needs one of these, it is being over-built.

## Testing approach

`tests/vulnerable_samples/` holds intentionally vulnerable code used as ground truth. Evaluation compares, per known vulnerability: did Semgrep detect it, did the analyzer find the right related files, was the source/sink pair correct, and did the AI classify it correctly (section 20).
