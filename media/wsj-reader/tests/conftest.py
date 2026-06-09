import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fx():
    def _load(name: str):
        text = (FIXTURES / name).read_text()
        if name.endswith(".json"):
            return json.loads(text)
        return text
    return _load


@pytest.fixture
def tmp_cache_dir(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setenv("WSJ_CACHE_DIR", str(cache))
    return cache


@pytest.fixture
def fake_env(monkeypatch, tmp_cache_dir):
    monkeypatch.setenv("WSJ_COOKIE", "fake-cookie-jar; many=values; here=for-tests; needs=padding-padding-padding-padding")
    monkeypatch.setenv("WSJ_REQUEST_SPACING_MS", "100")
    yield
