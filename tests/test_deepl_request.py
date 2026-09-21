import json

import pytest

from parfum.deepl import (MAX_ELEMENTS, Translation, build_batches, build_request,
                          load_instructions, parse_response)


def test_build_batches_caps_at_fifty_elements():
    batches = build_batches(["kurz"] * 120)
    assert [len(b) for b in batches] == [50, 50, 20]
    assert batches[1][0] == 50            # indices, not texts


def test_build_batches_caps_on_request_size():
    big = "x" * 60_000
    batches = build_batches([big, big, big])
    assert all(len(json.dumps({"text": [big] * len(b)}).encode()) <= 131072
               for b in batches)
    assert len(batches) == 3 or len(batches) == 2


def test_build_batches_never_drops_or_reorders_an_index():
    flat = [i for b in build_batches(["s"] * 137) for i in b]
    assert flat == list(range(137))


def test_build_request_sets_every_required_parameter():
    body = build_request(["Der Gestank."], context="Paris, 1738.",
                         glossary_id="gl-1", instructions=["Keep register formal."])
    assert body["text"] == ["Der Gestank."]
    assert body["source_lang"] == "DE"
    assert body["target_lang"] == "EN-US"
    assert body["split_sentences"] == "0"
    assert body["model_type"] == "quality_optimized"
    assert body["show_billed_characters"] is True
    assert body["context"] == "Paris, 1738."
    assert body["glossary_id"] == "gl-1"


def test_build_request_omits_glossary_and_context_when_absent():
    body = build_request(["Der Gestank."], context=None,
                         glossary_id=None, instructions=[])
    assert "glossary_id" not in body
    assert "context" not in body


def test_load_instructions_rejects_too_many(tmp_path):
    path = tmp_path / "i.json"
    path.write_text(json.dumps(["ok"] * 11), encoding="utf-8")
    with pytest.raises(ValueError, match="at most 10"):
        load_instructions(path)


def test_load_instructions_rejects_an_overlong_entry(tmp_path):
    path = tmp_path / "i.json"
    path.write_text(json.dumps(["x" * 301]), encoding="utf-8")
    with pytest.raises(ValueError, match="300 characters"):
        load_instructions(path)


def test_parse_response_reads_text_and_billing():
    payload = {"translations": [
        {"text": "The stench.", "billed_characters": 12,
         "model_type_used": "quality_optimized"}]}
    assert parse_response(payload) == [Translation("The stench.", 12, "quality_optimized")]
