import re

import pytest
import responses

from wsj_reader.client import NotFoundError, SessionExpiredError, UpstreamError, WSJClient


@responses.activate
def test_get_html_sends_cookie_and_browser_headers(fake_env):
    url = "https://www.wsj.com/print-edition/20260608/frontpage"
    responses.add(responses.GET, url, body="<html>ok</html>", status=200,
                  content_type="text/html")
    body = WSJClient().get_html(url, space=False)
    assert body.startswith("<html>")
    req = responses.calls[0].request
    assert req.headers["Cookie"].startswith("fake-cookie-jar")
    assert req.headers["Sec-Fetch-Site"] == "same-origin"
    assert req.headers["Sec-Fetch-Mode"] == "navigate"
    assert req.headers["Sec-Fetch-Dest"] == "document"
    assert req.headers["Referer"] == "https://www.wsj.com/"


def test_missing_cookie_is_lazy_not_fatal_at_init(monkeypatch, tmp_path):
    """WSJClient() now allows construction without WSJ_COOKIE — only the HTML
    transport needs it. GraphQL works without."""
    monkeypatch.setenv("WSJ_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("WSJ_COOKIE", raising=False)
    # Constructor must not raise.
    c = WSJClient(env_loaded=True)
    # But touching cookie_header (e.g. via get_html) must.
    with pytest.raises(SessionExpiredError):
        _ = c.cookie_header


@responses.activate
def test_graphql_get_sends_apollo_headers_no_cookie(monkeypatch, tmp_path):
    """GraphQL transport must not require WSJ_COOKIE."""
    monkeypatch.setenv("WSJ_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("WSJ_COOKIE", raising=False)
    monkeypatch.setenv("WSJ_REQUEST_SPACING_MS", "100")
    responses.add(
        responses.GET,
        re.compile(r"https://shared-data\.dowjones\.io/gateway/graphql.*"),
        json={"data": {"foo": "bar"}}, status=200,
    )
    c = WSJClient(env_loaded=True)
    result = c.graphql_get("deadbeef", {"x": 1}, space=False)
    assert result == {"data": {"foo": "bar"}}
    req = responses.calls[0].request
    assert req.headers["apollographql-client-name"] == "wsj-generator-olympia"
    assert req.headers["apollographql-client-version"] == "article"
    # No Cookie header at all.
    assert "Cookie" not in req.headers
    # The persisted-query envelope landed in the URL.
    assert "persistedQuery" in req.url
    assert "deadbeef" in req.url


@responses.activate
def test_graphql_error_response_raises(fake_env):
    responses.add(
        responses.GET,
        re.compile(r"https://shared-data\.dowjones\.io/gateway/graphql.*"),
        json={"data": None, "errors": [{"message": "boom"}]},
        status=200,
    )
    with pytest.raises(UpstreamError, match="boom"):
        WSJClient().graphql_get("deadbeef", space=False)


@responses.activate
def test_401_maps_to_session_expired(fake_env):
    url = "https://www.wsj.com/secret"
    responses.add(responses.GET, url, body="forbidden", status=401)
    with pytest.raises(SessionExpiredError):
        WSJClient().get_html(url, space=False)


@responses.activate
def test_404_maps_to_not_found(fake_env):
    url = "https://www.wsj.com/missing"
    responses.add(responses.GET, url, body="", status=404)
    with pytest.raises(NotFoundError):
        WSJClient().get_html(url, space=False)


@responses.activate
def test_429_then_success_backoff(fake_env, monkeypatch):
    monkeypatch.setattr("wsj_reader.client.time.sleep", lambda *_: None)
    url = "https://video-api.shdsvc.dowjones.io/api/legacy/find-all-videos"
    responses.add(responses.GET, url, body="too many", status=429)
    responses.add(responses.GET, url, json={"items": []}, status=200)
    assert WSJClient().get_json(url, space=False) == {"items": []}


@responses.activate
def test_fetch_budget_enforced(fake_env, monkeypatch):
    monkeypatch.setenv("WSJ_MAX_FETCHES", "1")
    url1 = "https://www.wsj.com/a"
    url2 = "https://www.wsj.com/b"
    responses.add(responses.GET, url1, body="ok", status=200, content_type="text/html")
    responses.add(responses.GET, url2, body="ok", status=200, content_type="text/html")
    c = WSJClient()
    c.get_html(url1, space=False)
    with pytest.raises(UpstreamError):
        c.get_html(url2, space=False)
