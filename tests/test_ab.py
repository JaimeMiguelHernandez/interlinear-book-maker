from parfum.ab import Divergence, compare, report
from parfum.deepl import Translation, Usage
from parfum.glossary import Entry
from parfum.model import Book, Kapitel, Satz, Sektion, Teil

ENTRIES = [Entry("Gestank", "stench", "w: stench")]


def _book():
    return Book(teile=[Teil(id="T1", number=1, kapitel=[
        Kapitel(id="T1.K01", number=1, sektionen=[
            Sektion(id="T1.K01.S01", saetze=[
                Satz("T1.K01.S01.s001", "Der Gestank."),
                Satz("T1.K01.S01.s002", "Der Gerber arbeitete."),
            ])])])])


class GlossaryAwareClient:
    """Renders 'Gestank' as 'smell' without the glossary, 'stench' with it."""

    def usage(self):
        return Usage(0, 500_000)

    def translate(self, texts, *, context, glossary_id, instructions):
        word = "stench" if glossary_id else "smell"
        return [Translation(t.replace("Gestank", word), len(t), "quality_optimized")
                for t in texts]


def test_compare_returns_only_the_rows_the_glossary_changed(tmp_path):
    diffs = compare(_book(), ENTRIES, [], GlossaryAwareClient(),
                    scope="T1.K01", glossary_id="gl-1", cache_root=tmp_path)
    assert [d.satz_id for d in diffs] == ["T1.K01.S01.s001"]
    assert diffs[0].without.endswith("smell.")
    assert diffs[0].with_.endswith("stench.")


def test_report_names_ids_and_counts_but_no_sentence_text():
    text = report([Divergence("T1.K01.S01.s001", "The smell.", "The stench.")])
    assert "1 of" in text or "changed: 1" in text
    assert "T1.K01.S01.s001" in text
    assert "smell" not in text and "stench" not in text
