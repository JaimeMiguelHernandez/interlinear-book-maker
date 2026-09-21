from parfum.candidates import Candidate, count_lemmas, monosemous, recurring
from parfum.model import Book, Kapitel, Satz, Sektion, Teil
from parfum.sentences import load_nlp
from parfum.wiktextract import Sense


def _book(*sentences):
    return Book(teile=[Teil(id="T1", number=1, kapitel=[
        Kapitel(id="T1.K01", number=1, sektionen=[
            Sektion(id="T1.K01.S01", saetze=[
                Satz(id=f"T1.K01.S01.s{i:03d}", text=t)
                for i, t in enumerate(sentences, start=1)
            ])
        ])
    ])])


def test_count_lemmas_folds_inflections_together():
    book = _book("Der Gerber arbeitet.", "Die Gerber arbeiten.", "Dem Gerber gefällt es.")
    counts = {c.lemma: c.count for c in count_lemmas(book, load_nlp())}
    assert counts["Gerber"] == 3


def test_count_lemmas_returns_descending_order():
    book = _book("Der Gerber und der Gerber.", "Ein Zug.")
    result = count_lemmas(book, load_nlp())
    assert [c.count for c in result] == sorted([c.count for c in result], reverse=True)


def test_recurring_applies_the_occurrence_floor():
    cands = [Candidate("Gerber", "NOUN", 9), Candidate("Zug", "NOUN", 3)]
    assert [c.lemma for c in recurring(cands, min_count=8)] == ["Gerber"]


def test_monosemous_drops_polysemous_and_unknown_lemmas():
    cands = [Candidate("Gerber", "NOUN", 9),
             Candidate("Zug", "NOUN", 9),
             Candidate("Grenouille", "PROPN", 9)]
    senses = {"Gerber": [Sense("noun", "tanner")],
              "Zug": [Sense("noun", "train"), Sense("noun", "draught")]}
    assert [c.lemma for c in monosemous(cands, senses)] == ["Gerber"]
