from parfum.cache import Cache, key
from parfum.deepl import Translation
from parfum.glossary import Entry

ENTRIES = [Entry("Gestank", "stench", "w: stench"),
           Entry("Gerber", "tanner", "w: tanner")]
INSTR = ["Keep register formal."]


def test_key_is_stable_across_runs():
    assert key("Der Gestank.", ENTRIES, "quality_optimized", INSTR) == \
           key("Der Gestank.", ENTRIES, "quality_optimized", INSTR)


def test_key_ignores_glossary_entries_absent_from_the_sentence():
    only_relevant = [Entry("Gestank", "stench", "w: stench")]
    assert key("Der Gestank.", ENTRIES, "quality_optimized", INSTR) == \
           key("Der Gestank.", only_relevant, "quality_optimized", INSTR)


def test_changing_an_unrelated_entry_does_not_invalidate_a_sentence():
    changed = [ENTRIES[0], Entry("Gerber", "currier", "w: currier")]
    assert key("Der Gestank.", ENTRIES, "quality_optimized", INSTR) == \
           key("Der Gestank.", changed, "quality_optimized", INSTR)


def test_changing_a_relevant_entry_does_invalidate_a_sentence():
    changed = [Entry("Gestank", "stink", "w: stink"), ENTRIES[1]]
    assert key("Der Gestank.", ENTRIES, "quality_optimized", INSTR) != \
           key("Der Gestank.", changed, "quality_optimized", INSTR)


def test_changing_the_instruction_set_invalidates_everything():
    assert key("Der Gestank.", ENTRIES, "quality_optimized", INSTR) != \
           key("Der Gestank.", ENTRIES, "quality_optimized", ["Other."])


def test_cache_round_trips_and_totals_billing(tmp_path):
    cache = Cache(tmp_path)
    k = key("Der Gestank.", ENTRIES, "quality_optimized", INSTR)
    assert cache.get(k) is None
    cache.put(k, Translation("The stench.", 12, "quality_optimized"))
    assert cache.get(k) == Translation("The stench.", 12, "quality_optimized")
    assert cache.billed_total() == 12
