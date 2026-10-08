from interlinear_book_maker.ab import Divergence, compare, report
from interlinear_book_maker.claude_cli import MODEL, Translation
from interlinear_book_maker.glossary import Entry
from interlinear_book_maker.model import Book, Kapitel, Satz, Sektion, Teil

ENTRIES = [Entry("Gestank", "stench", "w: stench")]


def _book():
    return Book(teile=[Teil(id="T1", number=1, kapitel=[
        Kapitel(id="T1.K01", number=1, sektionen=[
            Sektion(id="T1.K01.S01", saetze=[
                Satz("T1.K01.S01.s001", "Der Gestank."),
                Satz("T1.K01.S01.s002", "Der Gerber arbeitete."),
            ])])])])


class GlossaryAwareClient:
    """Renders 'Gestank' as 'smell' with no entries, 'stench' with them."""

    def translate(self, texts, *, context, entries, instructions):
        word = "stench" if entries else "smell"
        return ([Translation(t.replace("Gestank", word), MODEL) for t in texts],
                len(texts))


def test_compare_returns_only_the_rows_the_glossary_changed(tmp_path):
    diffs = compare(_book(), ENTRIES, [], GlossaryAwareClient(),
                    scope="T1.K01", cache_root=tmp_path)
    assert [d.satz_id for d in diffs] == ["T1.K01.S01.s001"]


def test_report_names_ids_and_counts_but_no_sentence_text():
    text = report([Divergence("T1.K01.S01.s001", "The smell.", "The stench.")])
    assert "1 of" in text or "changed: 1" in text
    assert "T1.K01.S01.s001" in text
    assert "smell" not in text and "stench" not in text
