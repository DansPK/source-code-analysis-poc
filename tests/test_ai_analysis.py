"""M6: the model's verdict, and the checks that stop it being taken on trust.

Everything here runs on canned or fake clients -- no API key, no network.
"""

import pytest

from app.ai import AIError
from app.ai.analyzer import analyze
from app.ai.client import MockClient, OpenAICompatibleClient, get_client
from app.ai.prompts import SYSTEM_PROMPT, render_context
from app.ai.validator import validate
from app.config.settings import Settings
from app.models import AIAnalysis, Finding, FindingContext, Repository, SourceFile

GOOD_RESPONSE = {
    "vulnerability_type": "SQL Injection",
    "status": "Likely Vulnerable",
    "severity": "High",
    "confidence": "High",
    "source": "request parameter",
    "sink": "execute()",
    "evidence": "Concatenated into the statement with no parameterization.",
    "protection_found": "None.",
    "impact": "Arbitrary rows readable.",
}


class FakeClient:
    """Returns each queued reply in turn, recording what it was asked."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def complete_json(self, system, user):
        self.prompts.append((system, user))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def repository():
    return Repository(
        root="/project",
        languages=["python"],
        frameworks=["flask"],
        files=[
            SourceFile(path="routes/search.py", language="python"),
            SourceFile(path="services/search_service.py", language="python"),
            SourceFile(path="database/user_repository.py", language="python"),
        ],
    )


@pytest.fixture
def context():
    return FindingContext(
        finding=Finding(
            id="F-001",
            file="database/user_repository.py",
            line=17,
            rule_id="python-sqli-concat",
            vulnerability_type="SQL Injection",
            scanner_severity="WARNING",
            message="Concatenated SQL reaches execute().",
        ),
        function_source="def search_users_by_name(name): ...",
        flow_chain=[
            "routes/search.py",
            "services/search_service.py",
            "database/user_repository.py",
        ],
    )


# --- analyzer -------------------------------------------------------------------


def test_facts_we_already_know_are_filled_in_from_context(context, repository):
    """The model judges security; the flow comes from our own analysis."""
    analysis = analyze(FakeClient(GOOD_RESPONSE), context, repository)

    assert analysis.data_flow == context.flow_chain
    assert analysis.sink_file == "database/user_repository.py"
    assert analysis.source_file == "routes/search.py"


def test_model_supplied_flow_is_left_alone(context, repository):
    reply = GOOD_RESPONSE | {"data_flow": ["a.py"], "source_file": "a.py", "sink_file": "b.py"}
    analysis = analyze(FakeClient(reply), context, repository)
    assert analysis.data_flow == ["a.py"] and analysis.source_file == "a.py"


def test_invalid_reply_is_retried_then_falls_back(context, repository):
    """Two bad replies must not crash the scan, and must not invent a verdict."""
    client = FakeClient({"status": "Definitely Exploitable"}, {"nonsense": True})

    analysis = analyze(client, context, repository)

    assert len(client.prompts) == 2
    assert analysis.status == "Needs Manual Review"
    assert analysis.confidence == "Low"
    assert analysis.data_flow == context.flow_chain  # context is still reported


def test_retry_prompt_tells_the_model_what_went_wrong(context, repository):
    client = FakeClient({"bad": True}, GOOD_RESPONSE)
    analyze(client, context, repository)
    assert "not valid" in client.prompts[1][0]
    assert client.prompts[0][0] == SYSTEM_PROMPT  # first attempt is the plain prompt


def test_transport_failure_falls_back_rather_than_raising(context, repository):
    client = FakeClient(AIError("connection refused"), AIError("connection refused"))
    assert analyze(client, context, repository).status == "Needs Manual Review"


# --- validator ------------------------------------------------------------------


def test_sound_analysis_passes_through_untouched(context, repository):
    analysis = analyze(FakeClient(GOOD_RESPONSE), context, repository)
    assert validate(analysis, context, repository) == analysis


@pytest.mark.parametrize("field", ["source_file", "sink_file"])
def test_hallucinated_file_is_downgraded(context, repository, field):
    analysis = AIAnalysis.model_validate(
        GOOD_RESPONSE | {"data_flow": [], field: "app/imaginary.py"}
    )

    validated = validate(analysis, context, repository)

    assert validated.status == "Needs Manual Review"
    assert validated.confidence == "Low"
    assert "not a file in this project" in validated.evidence


def test_hallucinated_flow_step_is_downgraded(context, repository):
    analysis = AIAnalysis.model_validate(
        GOOD_RESPONSE | {"data_flow": ["routes/search.py", "does/not/exist.py"]}
    )
    assert validate(analysis, context, repository).status == "Needs Manual Review"


def test_vulnerable_verdict_without_evidence_is_downgraded(context, repository):
    analysis = AIAnalysis.model_validate(GOOD_RESPONSE | {"evidence": "  ", "data_flow": []})
    validated = validate(analysis, context, repository)
    assert validated.status == "Needs Manual Review"
    assert "no evidence" in validated.evidence


def test_validator_never_raises_a_verdict(context, repository):
    """It may only lower. A cautious answer stays cautious."""
    analysis = AIAnalysis.model_validate(
        GOOD_RESPONSE | {"status": "Likely False Positive", "confidence": "Low", "data_flow": []}
    )
    validated = validate(analysis, context, repository)
    assert validated.status == "Likely False Positive" and validated.confidence == "Low"


# --- client and prompt ----------------------------------------------------------


def test_mock_client_matches_on_vulnerability_type():
    client = MockClient()
    assert client.complete_json("", "FINDING: SQL Injection")["severity"] == "High"
    assert client.complete_json("", "FINDING: Odd Thing")["status"] == "Needs Manual Review"


def test_mock_is_selected_by_settings():
    assert isinstance(get_client(Settings(llm_mock=True)), MockClient)


def test_real_client_without_a_key_says_what_to_do():
    with pytest.raises(AIError, match="--mock"):
        OpenAICompatibleClient(Settings(llm_mock=False, llm_api_key=""))


def test_prompt_lists_the_allowed_values_from_the_model():
    """Derived from AIAnalysis, so the prompt cannot drift from what validates."""
    for status in ("Likely Vulnerable", "Likely False Positive", "Needs Manual Review"):
        assert status in SYSTEM_PROMPT
    for field in AIAnalysis.model_fields:
        assert field in SYSTEM_PROMPT


def test_rendered_context_carries_the_cross_file_chain(context, repository):
    rendered = render_context(context, repository)
    assert "routes/search.py -> services/search_service.py" in rendered
    assert "python using flask" in rendered
    assert "database/user_repository.py:17" in rendered
