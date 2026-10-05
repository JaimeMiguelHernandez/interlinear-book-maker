import json

from interlinear_book_maker.cache import Cache, key
from interlinear_book_maker.claude_cli import MODEL, AlignmentError, TransportError, Translation
from interlinear_book_maker.glossary import Entry
from interlinear_book_maker.model import Book, Kapitel, Satz, Sektion, Teil
from interlinear_book_maker.translate import context_for, run, write_translated

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
    def __init__(self, *, fail_after=None, error=TransportError):
        self.calls = 0
        self.fail_after = fail_after
        self.error = error

    def translate(self, texts, *, context, entries, instructions):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise self.error("stopped")
        return [Translation(f"EN:{t}", MODEL) for t in texts], len(texts)


def test_run_translates_every_sentence_keyed_by_satz_id(tmp_path):
    result = run(_book(), ENTRIES, INSTR, Cache(tmp_path), FakeClient())
    assert result.translated["T1.K01.S01.s001"] == "EN:Der Gestank."
    assert len(result.translated) == 3
    assert result.from_api == 3


def test_scope_restricts_the_run_to_one_kapitel(tmp_path):
    result = run(_book(), ENTRIES, INSTR, Cache(tmp_path), FakeClient(),
                 scope="T1.K01")
    assert set(result.translated) == {"T1.K01.S01.s001", "T1.K01.S01.s002"}


def test_a_second_run_spends_nothing(tmp_path):
    cache = Cache(tmp_path)
    run(_book(), ENTRIES, INSTR, cache, FakeClient())
    client = FakeClient()
    result = run(_book(), ENTRIES, INSTR, cache, client)
    assert client.calls == 0
    assert result.from_cache == 3 and result.from_api == 0


def test_transport_failure_keeps_completed_sentences_and_reports_where_it_stopped(tmp_path):
    cache = Cache(tmp_path)
    client = FakeClient(fail_after=0)
    result = run(_book(), ENTRIES, INSTR, cache, client)
    assert result.stopped_at is not None
    assert result.translated == {}


def test_transport_failure_mid_run_keeps_earlier_batches_cached(tmp_path):
    cache = Cache(tmp_path)
    client = FakeClient(fail_after=1)
    result = run(_big_book(), ENTRIES, INSTR, cache, client)
    assert result.stopped_at is not None
    assert len(result.translated) == 20
    assert result.translated["T1.K01.S01.s000"] == "EN:Satz Nummer 0."
    assert cache.get(key("Satz Nummer 0.", ENTRIES, MODEL, INSTR)) is not None


def test_a_misaligned_batch_stops_the_run_without_corrupting_the_cache(tmp_path):
    cache = Cache(tmp_path)
    client = FakeClient(fail_after=0, error=AlignmentError)
    result = run(_book(), ENTRIES, INSTR, cache, client)
    assert result.stopped_at is not None
    assert result.translated == {}
    assert cache.get(key("Der Gestank.", ENTRIES, MODEL, INSTR)) is None


def test_tokens_accumulate_across_batches(tmp_path):
    result = run(_big_book(), ENTRIES, INSTR, Cache(tmp_path), FakeClient())
    assert result.tokens == 51   # _big_book(n=51); FakeClient reports len(texts) per batch


def test_context_for_supplies_neighbouring_sentences():
    context = context_for(_book(), "T1.K01.S01.s002", window=1)
    assert "Der Gestank." in context
    assert "Der Gerber arbeitete." not in context   # the sentence itself is excluded


def test_write_translated_is_atomic_and_keyed_by_id(tmp_path):
    result = run(_book(), ENTRIES, INSTR, Cache(tmp_path), FakeClient())
    out = tmp_path / "translated.json"
    write_translated(result, out)
    assert json.loads(out.read_text(encoding="utf-8"))["T1.K01.S01.s001"] == "EN:Der Gestank."
    assert not list(tmp_path.glob("*.tmp"))
