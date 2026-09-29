"""The prompts. All wording lives here.

Each user prompt opens with a `TASK:` line naming what is being asked. That keeps the
three jobs distinguishable -- including to `MockClient`, which keys its canned replies
off it.

The analysis schema is derived from `AIAnalysis` rather than written out, so the prompt
and the model it must validate against cannot drift apart.
"""

from typing import get_args

from app.models import (
    AIAnalysis,
    Confidence,
    Finding,
    FindingContext,
    Repository,
    Severity,
    Status,
)

TASK_ANALYSIS = "analysis"
TASK_EXPLANATION = "explanation"
TASK_REMEDIATION = "remediation"


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
        f"TASK: {TASK_ANALYSIS}",
        "",
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


EXPLANATION_SYSTEM = """You are explaining a confirmed security finding to the developer who \
wrote the code. They know the language but are not a security specialist.

Write two short paragraphs, plain prose, no headings or bullet points:
1. What the code does with the untrusted value, naming the files it passes through.
2. Why that is dangerous, concretely -- what an attacker could actually do.

Do not restate the severity or confidence, do not hedge with "may possibly", and do not \
suggest a fix; that is asked for separately. Reply as JSON: {"explanation": "..."}"""

REMEDIATION_SYSTEM = """You are advising the developer how to fix a security finding.

Give a short, concrete recommendation: what to change, and where. Mention the specific \
technique (parameterized query, allowlist, escaping at the right layer) rather than generic \
advice like "validate input". If the real fix belongs in a different file from the one the \
scanner flagged, say which.

Recommend the change; do not write a patch or rewrite the file. Two or three sentences. \
Reply as JSON: {"suggested_fix": "..."}"""


def _finding_summary(finding: Finding, analysis: AIAnalysis) -> list[str]:
    return [
        f"VULNERABILITY: {analysis.vulnerability_type}",
        f"STATUS: {analysis.status} (severity {analysis.severity}, confidence {analysis.confidence})",
        f"SOURCE: {analysis.source or 'unknown'} in {analysis.source_file or 'unknown file'}",
        f"SINK: {analysis.sink or 'unknown'} at {finding.file}:{finding.line}",
        f"FLOW: {' -> '.join(analysis.data_flow) if analysis.data_flow else 'not established'}",
        f"PROTECTION FOUND: {analysis.protection_found or 'none reported'}",
        f"EVIDENCE: {analysis.evidence}",
        f"IMPACT: {analysis.impact}",
    ]


def render_for_explanation(context: FindingContext, analysis: AIAnalysis) -> str:
    parts = [f"TASK: {TASK_EXPLANATION}", ""] + _finding_summary(context.finding, analysis)
    if context.function_source:
        parts += ["", f"CODE AT THE SINK ({context.finding.file}):", context.function_source]
    for excerpt in context.callers:
        parts += ["", f"CALLER ({excerpt.file}:{excerpt.start_line}):", excerpt.content]
    return "\n".join(parts)


def render_for_remediation(context: FindingContext, analysis: AIAnalysis) -> str:
    parts = [f"TASK: {TASK_REMEDIATION}", ""] + _finding_summary(context.finding, analysis)
    if context.function_source:
        parts += ["", f"CODE TO FIX ({context.finding.file}):", context.function_source]
    return "\n".join(parts)
