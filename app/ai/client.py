"""Talking to the model.

Everything goes through `LLMClient`, so no other module imports a vendor SDK. Any
OpenAI-compatible endpoint works; `MockClient` runs the whole pipeline with no API key.
"""

import json
from pathlib import Path
from typing import Protocol

from app.ai import AIError
from app.config.settings import PROJECT_ROOT, Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

MOCK_RESPONSES = PROJECT_ROOT / "tests/fixtures/mock_responses.json"


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str) -> dict:
        """Return the model's reply parsed as JSON."""


class OpenAICompatibleClient:
    def __init__(self, settings: Settings):
        from openai import OpenAI  # imported here so the mock path needs no SDK

        if not settings.llm_api_key:
            raise AIError("LLM_API_KEY is not set. Use --mock to run without a key.")
        self._client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)
        self._model = settings.llm_model

    def complete_json(self, system: str, user: str) -> dict:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                temperature=0,
            )
        except Exception as exc:  # the SDK raises a family of connection/API errors
            raise AIError(f"LLM request failed: {exc}") from exc

        content = response.choices[0].message.content or ""
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise AIError(f"Model did not return JSON: {content[:200]}") from exc


class MockClient:
    """Canned replies, so the whole pipeline runs with no API key.

    Keyed by the prompt's `TASK:` line and then by vulnerability type. Analysis replies
    deliberately leave the file paths empty; the analyzer fills those from the context,
    which is where the trustworthy version of that information lives.
    """

    def __init__(self, responses_path: Path = MOCK_RESPONSES):
        self._responses = json.loads(responses_path.read_text(encoding="utf-8"))

    def complete_json(self, system: str, user: str) -> dict:
        task = next(
            (line.split(":", 1)[1].strip() for line in user.splitlines() if line.startswith("TASK:")),
            "analysis",
        )
        by_type = self._responses.get(task, self._responses["analysis"])
        for vulnerability_type, reply in by_type.items():
            if vulnerability_type != "default" and vulnerability_type.lower() in user.lower():
                return reply
        return by_type["default"]


def get_client(settings: Settings) -> LLMClient:
    if settings.llm_mock:
        logger.info("Using canned LLM responses (mock mode)")
        return MockClient()
    return OpenAICompatibleClient(settings)
