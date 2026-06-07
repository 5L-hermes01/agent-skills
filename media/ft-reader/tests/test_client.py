import pytest
import responses

from ft_reader.client import FTClient, SessionExpiredError, UpstreamError, NotFoundError


@responses.activate
def test_get_json_sends_cookies_and_headers(fake_env):
    responses.add(
        responses.GET,
        "https://app-api.ft.com/ping",
        json={"ok": True},
        status=200,
    )
    c = FTClient()
    assert c.get_json("https://app-api.ft.com/ping", space=False) == {"ok": True}
    req = responses.calls[0].request
    assert "FTSession_s=fake-session" in req.headers["Cookie"]
    assert "_csrf=fake-csrf" in req.headers["Cookie"]
    assert req.headers["Referer"] == "https://app.ft.com/"
    assert req.headers["Origin"] == "https://app.ft.com"


def test_missing_cookie_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("FT_CACHE_DIR", str(tmp_path))
    for k in ("FT_SESSION_S", "FT_CLIENT_SESSION_ID", "FT_APP_USER", "FT_CSRF"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(SessionExpiredError):
        FTClient(env_loaded=True)


@responses.activate
def test_403_maps_to_session_expired(fake_env):
    responses.add(
        responses.GET,
        "https://app-api.ft.com/secret",
        body="Forbidden",
        status=403,
    )
    c = FTClient()
    with pytest.raises(SessionExpiredError):
        c.get_json("https://app-api.ft.com/secret", space=False)


@responses.activate
def test_404_maps_to_not_found(fake_env):
    responses.add(
        responses.GET,
        "https://app-api.ft.com/missing",
        body="",
        status=404,
    )
    c = FTClient()
    with pytest.raises(NotFoundError):
        c.get_json("https://app-api.ft.com/missing", space=False)


@responses.activate
def test_429_then_success_backoff(fake_env, monkeypatch):
    # No real sleep in tests.
    monkeypatch.setattr("ft_reader.client.time.sleep", lambda *_: None)
    responses.add(
        responses.GET,
        "https://app-api.ft.com/slow",
        body="too many",
        status=429,
    )
    responses.add(
        responses.GET,
        "https://app-api.ft.com/slow",
        json={"ok": True},
        status=200,
    )
    c = FTClient()
    assert c.get_json("https://app-api.ft.com/slow", space=False) == {"ok": True}


@responses.activate
def test_fetch_budget_enforced(fake_env, monkeypatch):
    monkeypatch.setenv("FT_MAX_FETCHES", "1")
    responses.add(
        responses.GET, "https://app-api.ft.com/x", json={"a": 1}, status=200,
    )
    responses.add(
        responses.GET, "https://app-api.ft.com/y", json={"b": 2}, status=200,
    )
    c = FTClient()
    c.get_json("https://app-api.ft.com/x", space=False)
    with pytest.raises(UpstreamError):
        c.get_json("https://app-api.ft.com/y", space=False)
