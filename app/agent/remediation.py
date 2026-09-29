"""Recommend a fix (spec §11.2).

Advice only. Generating patches is out of scope for the POC, and the agent must never
return modified code.
"""

from app.ai import AIError
from app.ai.client import LLMClient
from app.ai.prompts import REMEDIATION_SYSTEM, render_for_remediation
from app.models import AIAnalysis, FindingContext
from app.utils.logging import get_logger

logger = get_logger(__name__)


def recommend_fix(client: LLMClient, context: FindingContext, analysis: AIAnalysis) -> str:
    try:
        reply = client.complete_json(
            REMEDIATION_SYSTEM, render_for_remediation(context, analysis)
        )
    except AIError as exc:
        logger.warning("No remediation for %s: %s", context.finding.id, exc)
        return ""
    return str(reply.get("suggested_fix", "")).strip()
