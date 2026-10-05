import json
from pathlib import Path

import pytest

from interlinear_book_maker.claude_cli import (MAX_INSTRUCTION_CHARS, MAX_INSTRUCTIONS, MODEL,
                               RESPONSE_SCHEMA, AlignmentError, Translation,
                               build_batches, build_request, load_instructions,
                               parse_response)
from interlinear_book_maker.glossary import Entry

ENTRIES = [Entry("Gestank", "stench", "w: stench"),
           Entry("Gerber", "tanner", "w: tanner")]
INSTR = ["Keep register formal."]
USAGE = {"input_tokens": 2, "cache_creation_input_tokens": 1180,
         "cache_read_input_tokens": 5, "output_tokens": 93}


def _payload(rows, usage=USAGE):
    return {"is_error": False, "structured_output": {"rows": rows}, "usage": usage}


def test_batches_are_capped_at_twenty():
    batches = build_batches([f"Satz {i}." for i in range(45)])
    assert [len(b) for b in batches] == [20, 20, 5]
    assert batches[1][0] == 20


def test_a_short_run_is_one_batch():
    assert build_batches(["Eins.", "Zwei."]) == [[0, 1]]


def test_request_numbers_the_sentences_one_based():
    _, numbered = build_request(["Der Gestank.", "Der Gerber."], context=None,
                                entries=[], instructions=[])
    assert numbered == "1. Der Gestank.\n2. Der Gerber."


def test_request_carries_only_the_glossary_terms_present_in_the_batch():
    system, _ = build_request(["Der Gestank."], context=None, entries=ENTRIES,
                              instructions=[])
    assert "Gestank = stench" in system
    assert "tanner" not in system


def test_request_marks_context_as_not_for_translation():
    system, numbered = build_request(["Der Gestank."], context="Es war ein Sommer.",
                                     entries=[], instructions=[])
    assert "Es war ein Sommer." in system
    assert "do not translate" in system.lower()
    assert "Es war ein Sommer." not in numbered


def test_request_carries_the_instructions_in_the_system_text():
    system, _ = build_request(["Der Gestank."], context=None, entries=[],
                              instructions=INSTR)
    assert "Keep register formal." in system


def test_schema_wraps_the_rows_in_an_object():
    assert RESPONSE_SCHEMA["type"] == "object"
    rows = RESPONSE_SCHEMA["properties"]["rows"]
    assert rows["type"] == "array"
    assert rows["items"]["required"] == ["id", "english"]


def test_parse_reassembles_by_id_not_by_position():
    rows = [{"id": 2, "english": "The tanner."}, {"id": 1, "english": "The stench."}]
    translations, _ = parse_response(_payload(rows), expected=2)
    assert [t.text for t in translations] == ["The stench.", "The tanner."]
    assert translations[0] == Translation("The stench.", MODEL)


def test_parse_counts_every_input_and_output_token():
    rows = [{"id": 1, "english": "The stench."}]
    _, tokens = parse_response(_payload(rows), expected=1)
    assert tokens == 2 + 1180 + 5 + 93


@pytest.mark.parametrize("rows", [
    [{"id": 1, "english": "One."}],                                   # missing id
    [{"id": 1, "english": "One."}, {"id": 1, "english": "Again."}],   # duplicate id
    [{"id": 1, "english": "One."}, {"id": 2, "english": "Two."},
     {"id": 3, "english": "Three."}],                                 # extra id
])
def test_misaligned_responses_raise(rows):
    with pytest.raises(AlignmentError):
        parse_response(_payload(rows), expected=2)


def test_a_reply_without_structured_output_raises_alignment_error():
    with pytest.raises(AlignmentError, match="structured_output"):
        parse_response({"is_error": False, "result": "Sorry, I cannot."}, expected=1)


def test_load_instructions_rejects_too_many(tmp_path):
    path = tmp_path / "i.json"
    path.write_text(json.dumps(["ok"] * (MAX_INSTRUCTIONS + 1)), encoding="utf-8")
    with pytest.raises(ValueError, match=f"at most {MAX_INSTRUCTIONS}"):
        load_instructions(path)


def test_load_instructions_rejects_an_overlong_entry(tmp_path):
    path = tmp_path / "i.json"
    path.write_text(json.dumps(["x" * (MAX_INSTRUCTION_CHARS + 1)]), encoding="utf-8")
    with pytest.raises(ValueError, match=f"{MAX_INSTRUCTION_CHARS} characters"):
        load_instructions(path)


def test_the_recorded_response_parses():
    payload = json.loads((Path(__file__).parent / "fixtures"
                          / "claude_batch_response.json").read_text(encoding="utf-8"))
    translations, tokens = parse_response(payload, expected=2)
    assert len(translations) == 2
    assert tokens > 0
