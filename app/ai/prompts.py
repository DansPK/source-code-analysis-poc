"""The prompt. All wording lives here.

The schema is derived from `AIAnalysis` rather than written out, so the prompt and the
model it must validate against cannot drift apart.
"""

from typing import get_args

from app.models import AIAnalysis, Confidence, FindingContext, Repository, Severity, Status


def _options(literal) -> str:
    return " | ".join(get_args(literal))


SYSTEM_PROMPT = f"""You are a security engineer reviewing one candidate finding from a \
static analysis tool. The tool matched a suspicious pattern; your job is to decide whether \
it is a real, reachable vulnerability in this application.

You are given the code around the finding and the call chain leading to it, gathered from \
the whole project. Reason only about what you are shown. Do not assume protections you \
cannot see, and do not invent files, functions or line numbers.

Judge in particular:
- Is the input attacker-controlled, and does it actually reach the dangerous operation?
- Is there validation, escaping, parameterization or an authorization check on the path?
- What could an attacker achieve if there is not?

If the evidence is thin or the path is unclear, say so with a lower status and confidence. \
An honest "Needs Manual Review" is more useful than a confident guess.

Reply with a single JSON object and nothing else, using exactly these keys:
{", ".join(AIAnalysis.model_fields)}

Allowed values:
- status: {_options(Status)}
- severity: {_options(Severity)}
- confidence: {_options(Confidence)}

`evidence` explains your reasoning in one or two sentences. `protection_found` names any \
mitigation you did find, or states plainly that there is none. `data_flow` lists the files \
the value passes through, in order."""


def render_context(context: FindingContext, repository: Repository) -> str:
    """Turn the gathered context into the compact text the model reads."""
    finding = context.finding
    parts = [
        f"PROJECT: {', '.join(repository.languages) or 'unknown'}"
        + (f" using {', '.join(repository.frameworks)}" if repository.frameworks else ""),
        "",
        f"FINDING: {finding.vulnerability_type} ({finding.scanner_severity})",
        f"REPORTED AT: {finding.file}:{finding.line}",
        f"SCANNER SAID: {finding.message}",
    ]

    if context.flow_chain:
        parts += ["", "CALL CHAIN (input arrives at the top):", " -> ".join(context.flow_chain)]

    if context.imports:
        parts += ["", f"IMPORTS IN {finding.file}: {', '.join(context.imports)}"]

    if context.function_source:
        parts += ["", f"FUNCTION CONTAINING THE FINDING ({finding.file}):", context.function_source]
    elif finding.code_snippet:
        parts += ["", f"CODE AT THE FINDING ({finding.file}):", finding.code_snippet]

    for excerpt in context.callers:
        parts += ["", f"CALLER ({excerpt.file}:{excerpt.start_line}):", excerpt.content]

    for excerpt in context.callees:
        parts += ["", f"CALLED FROM THERE ({excerpt.file}:{excerpt.start_line}):", excerpt.content]

    return "\n".join(parts)
