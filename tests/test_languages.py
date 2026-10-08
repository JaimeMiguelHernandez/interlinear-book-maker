from interlinear_book_maker import paths
from interlinear_book_maker.languages import DEFAULT, LANGUAGES, set_target, target_code


def test_english_when_no_language_was_chosen():
    assert not paths.SETTINGS.exists()
    assert target_code() == DEFAULT == "en"


def test_a_chosen_language_round_trips():
    assert set_target("es") is True
    assert target_code() == "es"
    assert set_target("es") is False


def test_every_language_has_an_english_and_a_native_name():
    assert LANGUAGES["es"] == ("Spanish", "Español")
    assert list(LANGUAGES) == ["en", "es", "fr", "it", "pt", "nl", "pl", "sv"]
    assert all(len(names) == 2 and all(names) for names in LANGUAGES.values())
