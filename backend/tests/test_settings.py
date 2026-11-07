from pathlib import Path

from pipeline import settings

BACKEND = Path(__file__).resolve().parent.parent


def test_local_data_dir_is_under_backend_not_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("SCOUT_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert settings.data_dir("cache") == BACKEND / "cache"
    assert settings.data_dir("runs") == BACKEND / "runs"


def test_vercel_data_dir_is_tmp(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("SCOUT_DATA_DIR", raising=False)
    assert settings.data_dir("runs") == Path("/tmp/target-scout/runs")


def test_explicit_data_dir_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("SCOUT_DATA_DIR", str(tmp_path))
    assert settings.data_dir("cache") == tmp_path / "cache"


def test_default_client_cache_follows_data_dir(monkeypatch, tmp_path):
    from pipeline.http import default_client
    monkeypatch.setenv("SCOUT_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SCOUT_CACHE_DIR", raising=False)
    c = default_client()
    assert c.write_dir == tmp_path / "cache"
    assert BACKEND / "data" / "demo_cache" in c.read_dirs
