import json
from pathlib import Path

import pytest

from parfum.deepl import Client, QuotaExceeded, Usage, preflight
from parfum.glossary import Entry

FIXTURES = Path(__file__).parent / "fixtures" / "deepl_responses"


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeTransport:
    """Replays recorded responses and records the requests it was given."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def _recorded(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_usage_reads_the_free_tier_ledger():
    transport = FakeTransport(FakeResponse(200, _recorded("usage.json")))
    usage = Client("key", transport).usage()
    assert usage == Usage(120000, 500000)
    assert usage.remaining == 380000


def test_translate_returns_one_result_per_input_in_order():
    transport = FakeTransport(FakeResponse(200, _recorded("translate_two.json")))
    results = Client("key", transport).translate(
        ["Der Gestank.", "Der Gerber arbeitete."],
        context=None, glossary_id=None, instructions=[])
    assert [t.text for t in results] == ["The stench.", "The tanner worked."]
    assert [t.billed_characters for t in results] == [12, 21]


def test_translate_sends_the_auth_header_and_the_free_host():
    transport = FakeTransport(FakeResponse(200, _recorded("translate_two.json")))
    Client("key", transport).translate(["a", "b"], context=None,
                                       glossary_id=None, instructions=[])
    _, url, kwargs = transport.calls[0]
    assert url.startswith("https://api-free.deepl.com/v2/translate")
    assert kwargs["headers"]["Authorization"] == "DeepL-Auth-Key key"


def test_quota_exhausted_is_not_retried():
    transport = FakeTransport(FakeResponse(456, {}))
    with pytest.raises(QuotaExceeded):
        Client("key", transport).translate(["a"], context=None,
                                           glossary_id=None, instructions=[])
    assert len(transport.calls) == 1


def test_rate_limit_is_retried_then_succeeds():
    transport = FakeTransport(FakeResponse(429, {}),
                              FakeResponse(200, _recorded("translate_two.json")))
    client = Client("key", transport, sleep=lambda _s: None)
    assert len(client.translate(["a", "b"], context=None,
                                glossary_id=None, instructions=[])) == 2
    assert len(transport.calls) == 2


def test_create_glossary_posts_two_column_tsv():
    transport = FakeTransport(FakeResponse(200, {"glossary_id": "gl-42"}))
    entries = [Entry("Gestank", "stench", "w: stench")]
    assert Client("key", transport).create_glossary("parfum", entries) == "gl-42"
    _, _, kwargs = transport.calls[0]
    assert kwargs["data"]["entries"] == "Gestank\tstench"
    assert kwargs["data"]["entries_format"] == "tsv"
    assert kwargs["data"]["target_lang"] == "EN"      # glossary pair is DE->EN


def test_preflight_refuses_a_batch_that_will_not_fit():
    result = preflight(["x" * 200_000, "y" * 200_000], Usage(120000, 500000))
    assert result.pending_characters == 400_000
    assert result.remaining == 380_000
    assert result.fits is False


def test_preflight_accepts_a_batch_that_fits():
    assert preflight(["x" * 1000], Usage(120000, 500000)).fits is True
