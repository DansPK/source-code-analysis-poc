"""Turn a verdict into prose a developer can act on (spec §11.1)."""

from collections.abc import Callable

from app.ai import AIError
from app.ai.client import LLMClient
from app.ai.json_stream import complete_streaming
from app.ai.prompts import EXPLANATION_SYSTEM, render_for_explanation
from app.models import AIAnalysis, FindingContext
from app.utils.logging import get_logger

logger = get_logger(__name__)


def explain(
    client: LLMClient,
    context: FindingContext,
    analysis: AIAnalysis,
    on_text: Callable[[str], None] | None = None,
) -> str:
    """`on_text` receives the text in pieces as the model writes it."""
    try:
        reply = complete_streaming(
            client, EXPLANATION_SYSTEM, render_for_explanation(context, analysis), "explanation", on_text
        )
    except AIError as exc:
        logger.warning("No explanation for %s: %s", context.finding.id, exc)
        return ""
    return str(reply.get("explanation", "")).strip()
