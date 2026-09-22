import json

import pytest

from parfum.gemini import (MODEL, AlignmentError, Translation, build_batches,
                           build_request, parse_response)
from parfum.glossary import Entry

ENTRIES = [Entry("Gestank", "stench", "w: stench"),
           Entry("Gerber", "tanner", "w: tanner")]
INSTR = ["Keep register formal."]


def _payload(rows, tokens=42):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(rows)}]}}],
            "usageMetadata": {"totalTokenCount": tokens}}


def test_batches_are_capped_at_twenty():
    batches = build_batches([f"Satz {i}." for i in range(45)])
    assert [len(b) for b in batches] == [20, 20, 5]
    assert batches[1][0] == 20


def test_a_short_run_is_one_batch():
    assert build_batches(["Eins.", "Zwei."]) == [[0, 1]]


def test_request_numbers_the_sentences_one_based():
    body = build_request(["Der Gestank.", "Der Gerber."], context=None,
                         entries=[], instructions=[])
    text = body["contents"][0]["parts"][0]["text"]
    assert "1. Der Gestank." in text
    assert "2. Der Gerber." in text


def test_request_carries_only_the_glossary_terms_present_in_the_batch():
    body = build_request(["Der Gestank."], context=None, entries=ENTRIES,
                         instructions=[])
    prompt = json.dumps(body, ensure_ascii=False)
    assert "stench" in prompt
    assert "tanner" not in prompt


def test_request_marks_context_as_not_for_translation():
    body = build_request(["Der Gestank."], context="Es war ein Sommer.",
                         entries=[], instructions=[])
    prompt = json.dumps(body, ensure_ascii=False)
    assert "Es war ein Sommer." in prompt
    assert "do not translate" in prompt.lower()


def test_request_asks_for_a_json_array_at_temperature_zero():
    body = build_request(["Der Gestank."], context=None, entries=[],
                         instructions=INSTR)
    config = body["generationConfig"]
    assert config["response_mime_type"] == "application/json"
    assert config["response_schema"]["type"] == "ARRAY"
    assert config["temperature"] == 0
    assert "Keep register formal." in json.dumps(body, ensure_ascii=False)


def test_parse_reassembles_by_id_not_by_position():
    rows = [{"id": 2, "english": "The tanner."}, {"id": 1, "english": "The stench."}]
    translations, tokens = parse_response(_payload(rows), expected=2)
    assert [t.text for t in translations] == ["The stench.", "The tanner."]
    assert tokens == 42
    assert translations[0] == Translation("The stench.", MODEL)


@pytest.mark.parametrize("rows", [
    [{"id": 1, "english": "One."}],                                   # missing id
    [{"id": 1, "english": "One."}, {"id": 1, "english": "Again."}],   # duplicate id
    [{"id": 1, "english": "One."}, {"id": 2, "english": "Two."},
     {"id": 3, "english": "Three."}],                                 # extra id
])
def test_misaligned_responses_raise(rows):
    with pytest.raises(AlignmentError):
        parse_response(_payload(rows), expected=2)


def test_non_json_body_raises_alignment_error():
    payload = {"candidates": [{"content": {"parts": [{"text": "Sorry, I cannot."}]}}]}
    with pytest.raises(AlignmentError):
        parse_response(payload, expected=1)


def test_empty_candidates_raise_alignment_error():
    with pytest.raises(AlignmentError):
        parse_response({"candidates": []}, expected=1)


def test_the_recorded_response_parses():
    payload = json.loads(
        (__import__("pathlib").Path(__file__).parent / "fixtures"
         / "gemini_batch_response.json").read_text(encoding="utf-8"))
    translations, tokens = parse_response(payload, expected=2)
    assert len(translations) == 2
    assert tokens > 0
