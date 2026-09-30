"""Streaming a JSON reply: show one field's prose while the model is still writing it."""

import json
import re
from collections.abc import Callable

from app.ai import AIError
from app.ai.client import LLMClient


class FieldStream:
    """Pull one string field out of a JSON reply while it is still arriving.

    The model replies with one JSON object, so a UI cannot simply print the stream.
    This tracks the point where the field's string starts and decodes it as it comes,
    which is enough to show prose appearing live. A reply without the field (an ask
    tool call has no `answer`) emits nothing.
    """

    def __init__(self, field: str):
        self._field = re.compile(rf'"{re.escape(field)}"\s*:\s*"')
        self._raw = ""
        self._start = -1   # index just after the opening quote of the answer value
        self._emitted = 0

    def feed(self, chunk: str) -> str:
        """Return whatever new answer text this chunk completed."""
        self._raw += chunk
        if self._start < 0:
            match = self._field.search(self._raw)
            if not match:
                return ""
            self._start = match.end()

        body = self._raw[self._start :]
        # Stop at the closing quote, ignoring escaped ones.
        end = 0
        while end < len(body):
            if body[end] == "\\":
                end += 2
                continue
            if body[end] == '"':
                break
            end += 1
        complete = body[:end]

        # Decode only up to the last complete escape, so a split "\u00e9" is not mangled.
        safe = complete
        for trailing in range(1, min(6, len(safe)) + 1):
            if "\\" in safe[-trailing:]:
                safe = safe[:-trailing]
                break
        try:
            text = json.loads(f'"{safe}"')
        except json.JSONDecodeError:
            return ""

        new, self._emitted = text[self._emitted :], len(text)
        return new


def complete_streaming(
    client: LLMClient, system: str, user: str, field: str, on_text: Callable[[str], None] | None
) -> dict:
    """One model call, parsed as JSON. With `on_text` and a client that can stream, the
    reply's `field` is also passed out piece by piece as it arrives."""
    if on_text is None or not hasattr(client, "stream_json"):
        return client.complete_json(system, user)

    raw, stream = "", FieldStream(field)
    for chunk in client.stream_json(system, user):
        raw += chunk
        text = stream.feed(chunk)
        if text:
            on_text(text)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIError(f"Model did not return JSON: {raw[:200]}") from exc
