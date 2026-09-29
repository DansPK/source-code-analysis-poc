"""Talking to the model.

Everything goes through `LLMClient`, so no other module imports a vendor SDK and any
OpenAI-compatible endpoint works.
"""

import json
from typing import Protocol

from app.ai import AIError
from app.config.settings import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str) -> dict:
        """Return the model's reply parsed as JSON."""


class OpenAICompatibleClient:
    def __init__(self, settings: Settings):
        from openai import OpenAI

        if not settings.llm_api_key:
            raise AIError("LLM_API_KEY is not set. Add it to .env to run a scan.")
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


def get_client(settings: Settings) -> LLMClient:
    return OpenAICompatibleClient(settings)
