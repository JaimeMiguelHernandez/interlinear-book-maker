import json

import pytest

from parfum.cache import Cache, key
from parfum.deepl import MODEL_TYPE, QuotaExceeded, Translation, Usage
from parfum.glossary import Entry
from parfum.model import Book, Kapitel, Satz, Sektion, Teil
from parfum.translate import context_for, run, write_translated

ENTRIES = [Entry("Gestank", "stench", "w: stench")]
INSTR = ["Keep register formal."]


def _book():
    return Book(teile=[Teil(id="T1", number=1, kapitel=[
        Kapitel(id="T1.K01", number=1, sektionen=[
            Sektion(id="T1.K01.S01", saetze=[
                Satz("T1.K01.S01.s001", "Der Gestank."),
                Satz("T1.K01.S01.s002", "Der Gerber arbeitete."),
            ])]),
        Kapitel(id="T1.K02", number=2, sektionen=[
            Sektion(id="T1.K02.S01", saetze=[
                Satz("T1.K02.S01.s001", "Ein anderer Satz."),
            ])]),
    ])])


def _big_book(n=51):
    saetze = [Satz(f"T1.K01.S01.s{i:03d}", f"Satz Nummer {i}.") for i in range(n)]
    return Book(teile=[Teil(id="T1", number=1, kapitel=[
        Kapitel(id="T1.K01", number=1, sektionen=[
            Sektion(id="T1.K01.S01", saetze=saetze)])])])


class FakeClient:
    def __init__(self, *, fail_after=None):
        self.calls = 0
        self.fail_after = fail_after

    def usage(self):
        return Usage(0, 500_000)

    def translate(self, texts, *, context, glossary_id, instructions):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise QuotaExceeded("spent")
        return [Translation(f"EN:{t}", len(t), "quality_optimized") for t in texts]


def test_run_translates_every_sentence_keyed_by_satz_id(tmp_path):
    result = run(_book(), ENTRIES, INSTR, Cache(tmp_path), FakeClient(), "gl-1")
    assert result.translated["T1.K01.S01.s001"] == "EN:Der Gestank."
    assert len(result.translated) == 3
    assert result.from_api == 3


def test_scope_restricts_the_run_to_one_kapitel(tmp_path):
    result = run(_book(), ENTRIES, INSTR, Cache(tmp_path), FakeClient(), "gl-1",
                 scope="T1.K01")
    assert set(result.translated) == {"T1.K01.S01.s001", "T1.K01.S01.s002"}


def test_a_second_run_spends_nothing(tmp_path):
    cache = Cache(tmp_path)
    run(_book(), ENTRIES, INSTR, cache, FakeClient(), "gl-1")
    client = FakeClient()
    result = run(_book(), ENTRIES, INSTR, cache, client, "gl-1")
    assert client.calls == 0
    assert result.from_cache == 3 and result.from_api == 0


def test_quota_exhaustion_keeps_completed_sentences_and_reports_where_it_stopped(tmp_path):
    cache = Cache(tmp_path)
    client = FakeClient(fail_after=0)
    result = run(_book(), ENTRIES, INSTR, cache, client, "gl-1")
    assert result.stopped_at is not None
    assert result.translated == {}


def test_quota_exhaustion_mid_run_keeps_earlier_batches_cached(tmp_path):
    cache = Cache(tmp_path)
    client = FakeClient(fail_after=1)
    book = _big_book()
    result = run(book, ENTRIES, INSTR, cache, client, "gl-1")
    assert result.stopped_at is not None
    assert len(result.translated) == 50
    assert result.translated["T1.K01.S01.s000"] == "EN:Satz Nummer 0."
    first_key = key("Satz Nummer 0.", ENTRIES, MODEL_TYPE, INSTR)
    assert cache.get(first_key) is not None


def test_preflight_refuses_a_run_that_cannot_fit(tmp_path):
    class Broke(FakeClient):
        def usage(self):
            return Usage(499_999, 500_000)

    with pytest.raises(RuntimeError, match="pre-flight"):
        run(_book(), ENTRIES, INSTR, Cache(tmp_path), Broke(), "gl-1")


def test_context_for_supplies_neighbouring_sentences():
    context = context_for(_book(), "T1.K01.S01.s002", window=1)
    assert "Der Gestank." in context
    assert "Der Gerber arbeitete." not in context   # the sentence itself is excluded


def test_write_translated_is_atomic_and_keyed_by_id(tmp_path):
    result = run(_book(), ENTRIES, INSTR, Cache(tmp_path), FakeClient(), "gl-1")
    out = tmp_path / "translated.json"
    write_translated(result, out)
    assert json.loads(out.read_text(encoding="utf-8"))["T1.K01.S01.s001"] == "EN:Der Gestank."
    assert not list(tmp_path.glob("*.tmp"))
