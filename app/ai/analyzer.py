"""Ask the model whether a candidate finding is real (spec §8).

The model answers about security meaning. Facts we already established -- which files
the flow passes through -- are filled in from the context rather than taken from the
model, because our own analysis is the trustworthy source for them.
"""

from pydantic import ValidationError

from app.ai import AIError
from app.ai.client import LLMClient
from app.ai.prompts import SYSTEM_PROMPT, render_context
from app.models import AIAnalysis, FindingContext, Repository
from app.utils.logging import get_logger

logger = get_logger(__name__)

RETRY_HINT = (
    "\n\nYour previous reply was not valid. Reply with one JSON object only, "
    "using exactly the keys and allowed values listed above."
)


def analyze(client: LLMClient, context: FindingContext, repository: Repository) -> AIAnalysis:
    """Return the model's verdict, or an honest fallback if it cannot give one."""
    user_prompt = render_context(context, repository)

    for attempt in (1, 2):
        system = SYSTEM_PROMPT if attempt == 1 else SYSTEM_PROMPT + RETRY_HINT
        try:
            return _ground(AIAnalysis.model_validate(client.complete_json(system, user_prompt)), context)
        except (AIError, ValidationError) as exc:
            logger.warning("Analysis attempt %d for %s failed: %s", attempt, context.finding.id, exc)

    return _fallback(context)


def _ground(analysis: AIAnalysis, context: FindingContext) -> AIAnalysis:
    """Fill in what we know for certain and the model may have left out."""
    if not analysis.data_flow:
        analysis.data_flow = context.flow_chain
    if not analysis.sink_file:
        analysis.sink_file = context.finding.file
    if not analysis.source_file and context.flow_chain:
        analysis.source_file = context.flow_chain[0]
    return analysis


def _fallback(context: FindingContext) -> AIAnalysis:
    """The model failed twice. Park the finding for a human rather than drop it."""
    finding = context.finding
    logger.error("No usable analysis for %s; marking for manual review", finding.id)
    return AIAnalysis(
        vulnerability_type=finding.vulnerability_type,
        status="Needs Manual Review",
        severity="Medium",
        confidence="Low",
        sink_file=finding.file,
        source_file=context.flow_chain[0] if context.flow_chain else "",
        data_flow=context.flow_chain,
        evidence="The model did not return a usable analysis, so this finding was not assessed.",
        protection_found="Not assessed.",
        impact="Not assessed.",
    )
