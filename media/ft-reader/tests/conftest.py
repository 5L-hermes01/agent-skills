import json
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fx():
    def _load(name: str):
        return json.loads((FIXTURES / name).read_text())
    return _load


@pytest.fixture
def tmp_cache_dir(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setenv("FT_CACHE_DIR", str(cache))
    return cache


@pytest.fixture
def fake_env(monkeypatch, tmp_cache_dir):
    """Populate the four required cookie env vars with fake values."""
    for k, v in {
        "FT_SESSION_S": "fake-session",
        "FT_CLIENT_SESSION_ID": "fake-client",
        "FT_APP_USER": "fake-user",
        "FT_CSRF": "fake-csrf",
        "FT_REQUEST_SPACING_MS": "100",
    }.items():
        monkeypatch.setenv(k, v)
    yield
