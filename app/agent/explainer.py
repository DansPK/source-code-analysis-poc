"""Turn a verdict into prose a developer can act on (spec §11.1)."""

from app.ai import AIError
from app.ai.client import LLMClient
from app.ai.prompts import EXPLANATION_SYSTEM, render_for_explanation
from app.models import AIAnalysis, FindingContext
from app.utils.logging import get_logger

logger = get_logger(__name__)


def explain(client: LLMClient, context: FindingContext, analysis: AIAnalysis) -> str:
    try:
        reply = client.complete_json(
            EXPLANATION_SYSTEM, render_for_explanation(context, analysis)
        )
    except AIError as exc:
        logger.warning("No explanation for %s: %s", context.finding.id, exc)
        return ""
    return str(reply.get("explanation", "")).strip()
