"""The user-facing layer (spec §11): explain the finding, recommend a fix."""

from app.agent.explainer import explain
from app.agent.remediation import recommend_fix
from app.ai.client import LLMClient
from app.models import AIAnalysis, FindingContext, ReportItem


def report_item(
    client: LLMClient, number: int, context: FindingContext, analysis: AIAnalysis
) -> ReportItem:
    """Produce the finished item. `number` gives the user-facing VULN-001 id."""
    return ReportItem(
        id=f"VULN-{number:03d}",
        finding=context.finding,
        context=context,
        analysis=analysis,
        explanation=explain(client, context, analysis),
        suggested_fix=recommend_fix(client, context, analysis),
    )
