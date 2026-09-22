from parfum.cache import Cache, key
from parfum.gemini import MODEL, Translation
from parfum.glossary import Entry

ENTRIES = [Entry("Gestank", "stench", "w: stench"),
           Entry("Gerber", "tanner", "w: tanner")]
INSTR = ["Keep register formal."]


def test_key_is_stable_across_runs():
    assert key("Der Gestank.", ENTRIES, MODEL, INSTR) == \
           key("Der Gestank.", ENTRIES, MODEL, INSTR)


def test_a_different_model_partitions_the_cache():
    assert key("Der Gestank.", ENTRIES, MODEL, INSTR) != \
           key("Der Gestank.", ENTRIES, "some-other-model", INSTR)


def test_cache_round_trips(tmp_path):
    cache = Cache(tmp_path)
    k = key("Der Gestank.", ENTRIES, MODEL, INSTR)
    assert cache.get(k) is None
    cache.put(k, Translation("The stench.", MODEL))
    assert cache.get(k) == Translation("The stench.", MODEL)


def test_key_ignores_glossary_entries_absent_from_the_sentence():
    only_relevant = [Entry("Gestank", "stench", "w: stench")]
    assert key("Der Gestank.", ENTRIES, MODEL, INSTR) == \
           key("Der Gestank.", only_relevant, MODEL, INSTR)


def test_changing_an_unrelated_entry_does_not_invalidate_a_sentence():
    changed = [ENTRIES[0], Entry("Gerber", "currier", "w: currier")]
    assert key("Der Gestank.", ENTRIES, MODEL, INSTR) == \
           key("Der Gestank.", changed, MODEL, INSTR)


def test_changing_a_relevant_entry_does_invalidate_a_sentence():
    changed = [Entry("Gestank", "stink", "w: stink"), ENTRIES[1]]
    assert key("Der Gestank.", ENTRIES, MODEL, INSTR) != \
           key("Der Gestank.", changed, MODEL, INSTR)


def test_changing_the_instruction_set_invalidates_everything():
    assert key("Der Gestank.", ENTRIES, MODEL, INSTR) != \
           key("Der Gestank.", ENTRIES, MODEL, ["Other."])
