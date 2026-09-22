import json

import pytest

from parfum.gemini import (BASE_URL, MODEL, BadRequest, Client, TransportError)


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def _ok(rows, tokens=7):
    return FakeResponse(200, {
        "candidates": [{"content": {"parts": [{"text": json.dumps(rows)}]}}],
        "usageMetadata": {"totalTokenCount": tokens},
    })


class Recorder:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def _client(transport):
    return Client("test-key", transport, sleep=lambda _seconds: None)


def test_translate_posts_to_the_model_endpoint_with_the_key_in_a_header():
    transport = Recorder(_ok([{"id": 1, "english": "The stench."}]))
    _client(transport).translate(["Der Gestank."], context=None, entries=[],
                                 instructions=[])
    method, url, kwargs = transport.calls[0]
    assert method == "POST"
    assert url == f"{BASE_URL}/models/{MODEL}:generateContent"
    assert kwargs["headers"]["x-goog-api-key"] == "test-key"
    assert "key=" not in url


def test_translate_returns_translations_and_the_token_count():
    transport = Recorder(_ok([{"id": 1, "english": "The stench."}], tokens=31))
    translations, tokens = _client(transport).translate(
        ["Der Gestank."], context=None, entries=[], instructions=[])
    assert translations[0].text == "The stench."
    assert tokens == 31


def test_a_429_is_retried_after_backoff():
    transport = Recorder(FakeResponse(429),
                         _ok([{"id": 1, "english": "The stench."}]))
    translations, _ = _client(transport).translate(
        ["Der Gestank."], context=None, entries=[], instructions=[])
    assert translations[0].text == "The stench."
    assert len(transport.calls) == 2


def test_a_503_is_retried():
    transport = Recorder(FakeResponse(503),
                         _ok([{"id": 1, "english": "The stench."}]))
    _client(transport).translate(["Der Gestank."], context=None, entries=[],
                                 instructions=[])
    assert len(transport.calls) == 2


def test_persistent_failure_raises_transport_error():
    transport = Recorder(*[FakeResponse(429) for _ in range(5)])
    with pytest.raises(TransportError):
        _client(transport).translate(["Der Gestank."], context=None, entries=[],
                                     instructions=[])
    assert len(transport.calls) == 5


def test_a_400_is_not_retried():
    transport = Recorder(FakeResponse(400, {"error": {"message": "bad schema"}}))
    with pytest.raises(BadRequest, match="bad schema"):
        _client(transport).translate(["Der Gestank."], context=None, entries=[],
                                     instructions=[])
    assert len(transport.calls) == 1


def test_a_403_is_not_retried():
    transport = Recorder(FakeResponse(403, {"error": {"message": "bad key"}}))
    with pytest.raises(BadRequest):
        _client(transport).translate(["Der Gestank."], context=None, entries=[],
                                     instructions=[])
    assert len(transport.calls) == 1


def test_backoff_sleeps_between_attempts():
    slept = []
    transport = Recorder(FakeResponse(429),
                         _ok([{"id": 1, "english": "The stench."}]))
    Client("k", transport, sleep=slept.append).translate(
        ["Der Gestank."], context=None, entries=[], instructions=[])
    assert len(slept) == 1 and slept[0] > 0
