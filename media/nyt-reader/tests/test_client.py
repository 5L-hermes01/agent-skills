import re

import pytest
import responses

from nyt_reader.client import NotFoundError, NYTClient, SessionExpiredError, UpstreamError


@responses.activate
def test_graphql_sends_cookies_and_static_headers(fake_env):
    responses.add(
        responses.GET,
        re.compile(r"https://samizdat-graphql\.nytimes\.com/graphql/v2.*"),
        json={"data": {"ok": True}},
        status=200,
    )
    c = NYTClient()
    out = c.graphql("TestOp", sha256_hash="deadbeef" * 8, variables={"x": 1}, space=False)
    assert out == {"data": {"ok": True}}
    req = responses.calls[0].request
    assert "nyt-a=fake-a" in req.headers["Cookie"]
    assert "NYT-S=fake-s" in req.headers["Cookie"]
    assert req.headers["nyt-app-type"] == "project-vi"
    assert req.headers["nyt-app-version"] == "0.0.5"
    assert len(req.headers["nyt-token"]) > 100  # the embedded blob
    # URL must carry persisted-query extensions.
    assert "operationName=TestOp" in req.url
    assert "persistedQuery" in req.url


def test_missing_cookie_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("NYT_CACHE_DIR", str(tmp_path))
    for k in ("NYT_A", "NYT_S", "NYT_JKIDD", "NYT_PURR", "NYT_B_SID"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(SessionExpiredError):
        NYTClient(env_loaded=True)


@responses.activate
def test_403_maps_to_session_expired(fake_env):
    responses.add(
        responses.GET,
        re.compile(r"https://samizdat-graphql\.nytimes\.com/.*"),
        body="forbidden", status=403,
    )
    with pytest.raises(SessionExpiredError):
        NYTClient().graphql("X", sha256_hash="abc", space=False)


@responses.activate
def test_404_maps_to_not_found(fake_env):
    responses.add(
        responses.GET,
        re.compile(r"https://www\.nytimes\.com/.*"),
        body="not found", status=404,
    )
    with pytest.raises(NotFoundError):
        NYTClient().get_html("https://www.nytimes.com/missing", space=False)


@responses.activate
def test_429_then_success_backoff(fake_env, monkeypatch):
    monkeypatch.setattr("nyt_reader.client.time.sleep", lambda *_: None)
    url_re = re.compile(r"https://samizdat-graphql\.nytimes\.com/.*")
    responses.add(responses.GET, url_re, body="slow", status=429)
    responses.add(responses.GET, url_re, json={"data": {"ok": True}}, status=200)
    out = NYTClient().graphql("X", sha256_hash="abc", space=False)
    assert out == {"data": {"ok": True}}


@responses.activate
def test_fetch_budget_enforced(fake_env, monkeypatch):
    monkeypatch.setenv("NYT_MAX_FETCHES", "1")
    url_re = re.compile(r"https://samizdat-graphql\.nytimes\.com/.*")
    responses.add(responses.GET, url_re, json={"data": {}}, status=200)
    responses.add(responses.GET, url_re, json={"data": {}}, status=200)
    c = NYTClient()
    c.graphql("X", sha256_hash="abc", space=False)
    with pytest.raises(UpstreamError):
        c.graphql("Y", sha256_hash="abc", space=False)
