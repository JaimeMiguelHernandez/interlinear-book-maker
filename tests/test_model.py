from interlinear_book_maker.model import Book, Kapitel, Satz, Sektion, Teil, satz_id


def tiny_book():
    satz = Satz(id=satz_id(1, 3, 2, 14), text="Ein Satz.")
    return Book(teile=[
        Teil(id="T1", number=1, kapitel=[
            Kapitel(id="T1.K03", number=3, sektionen=[
                Sektion(id="T1.K03.S02", saetze=[satz])
            ])
        ])
    ])


def test_id_format_is_exact():
    assert satz_id(1, 3, 2, 14) == "T1.K03.S02.s014"
    assert satz_id(4, 51, 10, 7) == "T4.K51.S10.s007"


def test_round_trips_through_json():
    original = tiny_book()
    assert Book.from_dict(original.to_dict()) == original


def test_iter_saetze_walks_in_reading_order():
    assert [s.id for s in tiny_book().iter_saetze()] == ["T1.K03.S02.s014"]


def test_iter_sektionen_yields_every_sektion():
    assert [s.id for s in tiny_book().iter_sektionen()] == ["T1.K03.S02"]
