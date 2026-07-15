from pathlib import Path

from src.utils import get_cache_dir


def test_get_cache_dir_returns_none_when_disabled():
    assert get_cache_dir({"cache": {"enabled": False}}) is None


def test_get_cache_dir_uses_enabled_path(tmp_path):
    cache_path = tmp_path / "scm-cache-test"

    path = get_cache_dir({"cache": {"enabled": True, "dir": str(cache_path)}})

    assert path == cache_path
    assert path.exists()
