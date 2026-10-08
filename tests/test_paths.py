from interlinear_book_maker import paths


def test_root_resolves_to_the_repository_root():
    assert (paths.ROOT / "pyproject.toml").is_file()
    assert (paths.ROOT / "src" / "interlinear_book_maker" / "paths.py").is_file()


def test_data_dirs_live_under_root():
    assert paths.DATA == paths.ROOT / "data"
    assert paths.RAW == paths.DATA / "raw"
    assert paths.REFERENCE == paths.DATA / "reference"
    assert paths.INTERIM == paths.DATA / "interim"
    assert paths.CACHE == paths.DATA / "cache"
    assert paths.OUTPUT == paths.DATA / "output"
    assert paths.TRANSLATION_CACHE == paths.DATA / "cache" / "translation"


def test_config_is_tracked_not_under_data():
    assert paths.CONFIG == paths.ROOT / "config"
    assert paths.DATA not in paths.CONFIG.parents


def test_ensure_dirs_is_idempotent(tmp_path):
    paths.ensure_dirs(tmp_path)
    paths.ensure_dirs(tmp_path)
    assert (tmp_path / "interim").is_dir()
    assert (tmp_path / "cache").is_dir()
