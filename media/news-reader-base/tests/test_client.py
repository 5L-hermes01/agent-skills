from __future__ import annotations

import pytest
import responses

from news_reader_base import (
    BaseClient,
    NotFoundError,
    SessionExpiredError,
    UpstreamError,
)


class _Client(BaseClient):
    SOURCE = "TEST"

    def _headers(self) -> dict:
        return {"User-Agent": self.user_agent, "X-Test": "1"}


@pytest.fixture(autouse=True)
def fast_spacing(monkeypatch):
    monkeypatch.setenv("TEST_REQUEST_SPACING_MS", "100")


@responses.activate
def test_get_json_ok():
    responses.get("https://api.test/x", json={"ok": True}, status=200)
    assert _Client().get_json("https://api.test/x", space=False) == {"ok": True}


@responses.activate
def test_session_expired_on_403():
    responses.get("https://api.test/x", status=403, body="forbidden")
    with pytest.raises(SessionExpiredError):
        _Client().get_json("https://api.test/x", space=False)


@responses.activate
def test_not_found_on_404():
    responses.get("https://api.test/x", status=404, body="nope")
    with pytest.raises(NotFoundError):
        _Client().get_json("https://api.test/x", space=False)


@responses.activate
def test_upstream_on_500():
    responses.get("https://api.test/x", status=500, body="boom")
    with pytest.raises(UpstreamError):
        _Client().get_json("https://api.test/x", space=False)


@responses.activate
def test_429_retries_then_succeeds():
    responses.get("https://api.test/x", status=429, body="slow down")
    responses.get("https://api.test/x", json={"ok": True}, status=200)
    assert _Client().get_json("https://api.test/x", space=False) == {"ok": True}


def test_budget_exhausted(monkeypatch):
    monkeypatch.setenv("TEST_MAX_FETCHES", "1")
    c = _Client()
    c._fetch_count = 1
    with pytest.raises(UpstreamError, match="budget exhausted"):
        c.get_json("https://api.test/x", space=False)


@responses.activate
def test_get_bytes_returns_body():
    responses.get("https://cdn.test/file.bin", body=b"\x00\x01\x02", status=200)
    assert _Client().get_bytes("https://cdn.test/file.bin", space=False) == b"\x00\x01\x02"


def test_concrete_exception_subclasses_propagate():
    """Source-specific subclasses bubble through raise_for_status."""
    class _FTExpired(SessionExpiredError):
        pass

    class _C(BaseClient):
        SOURCE = "FT"

        def _headers(self) -> dict:
            return {}

    c = _C(session_expired_cls=_FTExpired)
    with responses.RequestsMock() as r:
        r.get("https://api.test/x", status=401)
        with pytest.raises(_FTExpired):
            c.get_json("https://api.test/x", space=False)
