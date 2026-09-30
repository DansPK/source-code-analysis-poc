"""The user-facing layer (spec §11): explain the finding, recommend a fix."""

from collections.abc import Callable

from app.agent.explainer import explain
from app.agent.remediation import recommend_fix
from app.ai.client import LLMClient
from app.models import AIAnalysis, FindingContext, ReportItem


def report_item(
    client: LLMClient,
    number: int,
    context: FindingContext,
    analysis: AIAnalysis,
    on_text: Callable[[str, str], None] | None = None,
) -> ReportItem:
    """Produce the finished item. `number` gives the user-facing VULN-001 id.
    `on_text(field, text)` receives the explanation and the suggested fix as they are
    written, `field` being "explanation" or "suggested_fix"."""

    def stream(field: str) -> Callable[[str], None] | None:
        return (lambda text: on_text(field, text)) if on_text else None

    return ReportItem(
        id=f"VULN-{number:03d}",
        finding=context.finding,
        context=context,
        analysis=analysis,
        explanation=explain(client, context, analysis, stream("explanation")),
        suggested_fix=recommend_fix(client, context, analysis, stream("suggested_fix")),
    )
