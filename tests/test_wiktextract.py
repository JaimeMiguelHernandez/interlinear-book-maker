from pathlib import Path

from interlinear_book_maker.wiktextract import Sense, build_subset, load_subset, save_subset

FIXTURE = Path(__file__).parent / "fixtures" / "wiktextract_mini.jsonl"


def _lines():
    return FIXTURE.read_text(encoding="utf-8").splitlines()


def test_build_subset_keeps_only_wanted_german_words():
    senses = build_subset(_lines(), {"Gestank", "Zug", "train"})
    assert set(senses) == {"Gestank", "Zug"}          # "train" is lang_code en
    assert senses["Gestank"] == [Sense("noun", "stench, stink")]
    assert len(senses["Zug"]) == 3


def test_build_subset_ignores_malformed_lines():
    senses = build_subset(["not json", "", '{"word": "X"}'] + _lines(), {"Gestank"})
    assert set(senses) == {"Gestank"}


def test_subset_round_trips_through_disk(tmp_path):
    senses = build_subset(_lines(), {"Gestank", "Zug"})
    out = tmp_path / "senses.json"
    save_subset(senses, out)
    assert load_subset(out) == senses
