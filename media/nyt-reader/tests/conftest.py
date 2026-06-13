import json
import os
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
    monkeypatch.setenv("NYT_CACHE_DIR", str(cache))
    return cache


@pytest.fixture
def fake_env(monkeypatch, tmp_cache_dir):
    """Populate the five required cookie env vars with fake values."""
    for k, v in {
        "NYT_A": "fake-a",
        "NYT_S": "fake-s",
        "NYT_JKIDD": "fake-jkidd",
        "NYT_PURR": "fake-purr",
        "NYT_B_SID": "fake-b-sid",
        "NYT_REQUEST_SPACING_MS": "100",
    }.items():
        monkeypatch.setenv(k, v)
    yield
