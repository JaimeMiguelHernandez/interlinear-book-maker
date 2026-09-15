from parfum import paths


def test_data_dirs_live_under_root():
    assert paths.DATA == paths.ROOT / "data"
    assert paths.INTERIM == paths.DATA / "interim"
    assert paths.OUTPUT == paths.DATA / "output"


def test_ensure_dirs_is_idempotent(tmp_path):
    paths.ensure_dirs(tmp_path)
    paths.ensure_dirs(tmp_path)
    assert (tmp_path / "interim").is_dir()
    assert (tmp_path / "cache").is_dir()
