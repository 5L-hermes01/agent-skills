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


def test_missing_cookie_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("WSJ_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("WSJ_COOKIE", raising=False)
    with pytest.raises(SessionExpiredError):
        WSJClient(env_loaded=True)


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
