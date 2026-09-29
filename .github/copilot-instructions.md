# Copilot instructions

Full guidance lives in `AGENTS.md` at the repository root — read it before making
non-trivial changes. Copilot cannot import files, so the essentials are repeated here.

Built in milestones — **read `HANDOFF.md` first** for which one is current and what is
frozen. `AI_Source_Code_Vulnerability_Scanner_POC.md` is the authoritative spec and
`folder-structure.md` fixes the layout; follow those rather than inventing one.

**Keep it simple — this is a POC.** If you cannot name the caller, do not write it: no
speculative fields, helpers, options or abstractions. Models are plain data; logic goes in the
module whose job it is. No plugin systems, registries or async. Shorter and obvious beats
flexible.

Python 3.11, managed with **uv** (`uv sync`, `uv add <pkg>`, `uv run pytest`).

The scanner pipeline is strictly staged and the stages must stay separate:

```
Source Manager → Repository Analyzer → Static Scanner (Semgrep) → Finding Parser
  → Context Investigator → AI Analyzer → Validator → AI Agent → Report Engine
```

- Semgrep detects candidates; the LLM only reasons about whether a candidate is real.
  Never send a whole repository to the model and ask it to find bugs.
- `findings/parser.py` isolates Semgrep — everything downstream uses the normalized
  `Finding` model.
- Cross-file context (source of tainted input vs. sink) is the core feature, bounded
  to the affected function plus 1–2 levels of callers/callees plus related imports.
- The AI Analyzer returns structured data, not prose; prose comes from `agent/`.
- The Validator preserves uncertainty; the Agent recommends fixes but never patches code.
