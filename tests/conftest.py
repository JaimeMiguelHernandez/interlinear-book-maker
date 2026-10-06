import pytest

from interlinear_book_maker import paths


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    """No test reads or writes the working copy's data/settings.json."""
    monkeypatch.setattr(paths, "SETTINGS", tmp_path / "settings.json")
