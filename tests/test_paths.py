from parfum import paths


def test_root_resolves_to_the_repository_root():
    assert (paths.ROOT / "pyproject.toml").is_file()
    assert (paths.ROOT / "src" / "parfum" / "paths.py").is_file()


def test_data_dirs_live_under_root():
    assert paths.DATA == paths.ROOT / "data"
    assert paths.RAW == paths.DATA / "raw"
    assert paths.REFERENCE == paths.DATA / "reference"
    assert paths.INTERIM == paths.DATA / "interim"
    assert paths.CACHE == paths.DATA / "cache"
    assert paths.WORKORDERS == paths.DATA / "workorders"
    assert paths.OUTPUT == paths.DATA / "output"


def test_ensure_dirs_is_idempotent(tmp_path):
    paths.ensure_dirs(tmp_path)
    paths.ensure_dirs(tmp_path)
    assert (tmp_path / "interim").is_dir()
    assert (tmp_path / "cache").is_dir()
