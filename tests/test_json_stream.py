"""M13: showing one field of a JSON reply while the model is still writing it."""

import json

from app.ai.json_stream import FieldStream, complete_streaming


def feed_in_pieces(field: str, reply: dict, size: int) -> str:
    stream, text = FieldStream(field), ""
    raw = json.dumps(reply)
    for start in range(0, len(raw), size):
        text += stream.feed(raw[start : start + size])
    return text


def test_only_the_named_field_is_emitted():
    reply = {"status": "Likely Vulnerable", "explanation": "Line one.\nLine \"two\" – é.", "x": 1}
    for size in (1, 2, 3, 7, 50):  # splits land inside escapes and multibyte characters
        assert feed_in_pieces("explanation", reply, size) == reply["explanation"]


def test_a_reply_without_the_field_emits_nothing():
    assert feed_in_pieces("answer", {"tool": "read_file", "args": {"path": "a.py"}}, 3) == ""


class Streaming:
    def stream_json(self, system, user):
        yield from ['{"suggested_', 'fix": "Use a par', 'ameterized query."}']

    def complete_json(self, system, user):
        raise AssertionError("a caller that wants text must get the stream")


class NotStreaming:
    def complete_json(self, system, user):
        return {"suggested_fix": "Use a parameterized query."}


def test_complete_streaming_returns_the_parsed_reply_and_passes_the_text_on():
    pieces = []
    reply = complete_streaming(Streaming(), "s", "u", "suggested_fix", pieces.append)
    assert reply == {"suggested_fix": "Use a parameterized query."}
    assert "".join(pieces) == "Use a parameterized query."


def test_a_client_that_cannot_stream_still_answers():
    pieces = []
    assert complete_streaming(NotStreaming(), "s", "u", "suggested_fix", pieces.append)["suggested_fix"]
    assert pieces == []
