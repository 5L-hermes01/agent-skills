import re

import pytest
import responses

from wsj_reader.headlines import get_headlines


# ─── Homepage transport (default, no auth) ───────────────────────────────


@responses.activate
def test_headlines_homepage_default_works_without_cookie(monkeypatch, tmp_path, fx):
    monkeypatch.setenv("WSJ_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("WSJ_COOKIE", raising=False)
    responses.add(
        responses.GET,
        "https://www.wsj.com/",
        body=fx("homepage.html"),
        status=200,
        content_type="text/html",
    )
    out = get_headlines(limit=10)
    assert out["schema_version"] == 1
    assert out["via"] == "homepage"
    assert out["collection_id"] is None
    assert out["edition_date"] is None
    assert [a["headline"] for a in out["articles"]] == [
        "Synthetic homepage lead story",
        "Synthetic homepage second story",
        "Synthetic homepage feature",
    ]
    assert out["articles"][0]["section"] == "front"
    assert out["articles"][0]["byline"] == "Home Reporter"
    assert out["articles"][1]["byline"] == "By Second Reporter"
    assert "Cookie" not in responses.calls[0].request.headers


@responses.activate
def test_headlines_homepage_limit_and_dedupe(monkeypatch, tmp_path, fx):
    monkeypatch.setenv("WSJ_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("WSJ_COOKIE", raising=False)
    responses.add(
        responses.GET,
        "https://www.wsj.com/",
        body=fx("homepage.html"),
        status=200,
        content_type="text/html",
    )
    out = get_headlines(limit=2)
    assert [a["headline"] for a in out["articles"]] == [
        "Synthetic homepage lead story",
        "Synthetic homepage second story",
    ]


@responses.activate
def test_headlines_homepage_no_cache_does_not_write(monkeypatch, tmp_path, fx):
    monkeypatch.setenv("WSJ_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("WSJ_COOKIE", raising=False)
    responses.add(
        responses.GET,
        "https://www.wsj.com/",
        body=fx("homepage.html"),
        status=200,
        content_type="text/html",
    )
    out = get_headlines(limit=1, no_cache=True)
    assert out["articles"][0]["headline"] == "Synthetic homepage lead story"
    assert list(tmp_path.iterdir()) == []


def test_headlines_homepage_rejects_graphql_collection():
    with pytest.raises(ValueError, match="collection is only supported with via='graphql'"):
        get_headlines(collection="most-popular")


def test_headlines_homepage_rejects_audio_only():
    with pytest.raises(ValueError, match="audio_only is only supported with via='graphql'"):
        get_headlines(audio_only=True)


# ─── HTML transport (via="html") ─────────────────────────────────────────


@responses.activate
def test_headlines_html_extracts_print_edition(fake_env, fx):
    url_re = re.compile(r"https://www\.wsj\.com/print-edition/\d{8}/frontpage")
    responses.add(responses.GET, url_re, body=fx("print_edition.html"),
                  status=200, content_type="text/html")
    out = get_headlines(via="html", edition_date="20260608", limit=10)
    assert out["schema_version"] == 1
    assert out["via"] == "html"
    assert out["edition_date"] == "20260608"
    urls = [a["url"] for a in out["articles"]]
    assert "https://www.wsj.com/finance/test-article-one-aaaa1111" in urls
    assert "https://www.wsj.com/business/test-business-cccc3333" in urls
    front = [a for a in out["articles"] if a["section"] == "front"]
    biz = [a for a in out["articles"] if a["section"] == "business"]
    assert len(front) == 2
    assert len(biz) == 1


@responses.activate
def test_headlines_html_section_filter(fake_env, fx):
    url_re = re.compile(r"https://www\.wsj\.com/print-edition/\d{8}/frontpage")
    responses.add(responses.GET, url_re, body=fx("print_edition.html"),
                  status=200, content_type="text/html")
    out = get_headlines(via="html", edition_date="20260608", section="business")
    assert len(out["articles"]) == 1
    assert out["articles"][0]["section"] == "business"


@responses.activate
def test_headlines_html_walks_back_when_no_articles(fake_env, fx):
    empty_html = (
        '<html><script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"articles":[]}}}'
        '</script></html>'
    )
    url_re = re.compile(r"https://www\.wsj\.com/print-edition/(\d{8})/frontpage")
    call_count = {"n": 0}

    def cb(request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return (200, {"content-type": "text/html"}, empty_html)
        return (200, {"content-type": "text/html"}, fx("print_edition.html"))

    responses.add_callback(responses.GET, url_re, callback=cb)
    out = get_headlines(via="html", max_days_back=2)
    assert call_count["n"] == 2
    assert len(out["articles"]) >= 1


# ─── GraphQL transport (explicit collection mode) ────────────────────────


def _graphql_payload(items):
    return {"data": {"summaryCollectionContent": {
        "id": "MOST-POP-WSJ-NO-OPN_1",
        "collectionItems": items,
    }}}


def _gql_item(article_id, url, headline, summary="A short summary.",
              section="World", published="2026-06-08T00:00:00Z"):
    return {
        "id": article_id,
        "content": {
            "sectionName": section,
            "breakingNews": False,
            "sourceUrl": url,
            "publishedDateTimeUtc": published,
            "flattenedSummary": {
                "headline": {"text": headline},
                "flashline": None,
                "image": [{"src": {"baseUrl": "https://images.wsj.net/",
                                    "path": "im-xxx"}}],
            },
            "mobileSummary": {
                "description": {"content": {"text": summary}},
            },
        },
    }


@responses.activate
def test_headlines_graphql_default(fake_env, monkeypatch):
    """GraphQL collection mode still works when explicitly selected."""
    monkeypatch.setenv("WSJ_REQUEST_SPACING_MS", "100")
    # GraphQL response
    responses.add(
        responses.GET,
        re.compile(r"https://shared-data\.dowjones\.io/gateway/graphql.*"),
        json=_graphql_payload([
            _gql_item("WP-WSJ-0000000001",
                      "https://www.wsj.com/world/test-1",
                      "Test headline 1"),
            _gql_item("WP-WSJ-0000000002",
                      "https://www.wsj.com/business/test-2",
                      "Test headline 2", section="Business"),
        ]),
        status=200,
    )
    # Audio resolver — both available
    responses.add(
        responses.GET,
        re.compile(r"https://video-api\.shdsvc\.dowjones\.io/.*"),
        json={"items": [{
            "id": "{AAAAAAAA-1111-2222-3333-BBBBBBBBBBBB}",
            "duration": "240",
            "formattedCreationDate": "6/8/2026 5:00:00 PM",
            "author": "Test Reporter",
        }]},
        status=200,
    )
    # CDN probe — /1/ exists at the canonical size (240s * 128kbps / 8).
    responses.add(
        responses.GET,
        re.compile(r"https://m\.wsj\.net/audio/20260608/aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb/1/.*"),
        body=b"\x00" * 8, status=206,
        adding_headers={"Content-Range": f"bytes 0-7/{240 * 128_000 // 8}",
                         "Content-Type": "audio/mpeg"},
    )
    out = get_headlines(via="graphql", limit=5)
    assert out["schema_version"] == 1
    assert out["via"] == "graphql"
    assert out["collection_id"] == "MOST-POP-WSJ-NO-OPN_1"
    assert len(out["articles"]) == 2
    a = out["articles"][0]
    assert a["headline"] == "Test headline 1"
    assert a["article_id"] == "WP-WSJ-0000000001"
    assert a["section"] == "World"
    assert a["summary"] == "A short summary."
    assert a["audio_available"] is True
    assert a["audio_url"].endswith(
        "/aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb/1/ele-wp-wsj-0000000001-full.mp3"
    )
    assert a["audio_duration"] == 240
    assert a["byline"] == "Test Reporter"
    assert a["image_url"] == "https://images.wsj.net/im-xxx"


@responses.activate
def test_headlines_graphql_audio_only_filters(fake_env, monkeypatch):
    monkeypatch.setenv("WSJ_REQUEST_SPACING_MS", "100")
    responses.add(
        responses.GET,
        re.compile(r"https://shared-data\.dowjones\.io/gateway/graphql.*"),
        json=_graphql_payload([
            _gql_item("WP-WSJ-0000000003",
                      "https://www.wsj.com/world/no-audio",
                      "No audio"),
            _gql_item("WP-WSJ-0000000004",
                      "https://www.wsj.com/world/has-audio",
                      "Has audio"),
        ]),
        status=200,
    )
    # First call: empty items (no audio). Second: real item.
    call_count = {"n": 0}

    def audio_cb(request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return (200, {}, '{"items": []}')
        return (200, {}, '{"items": [{"id":"{X-X-X-X-X}","duration":"100",'
                          '"formattedCreationDate":"6/8/2026 5:00:00 PM",'
                          '"author":"R"}]}')
    responses.add_callback(
        responses.GET,
        re.compile(r"https://video-api\.shdsvc\.dowjones\.io/.*"),
        callback=audio_cb,
    )
    # The second item's CDN probe — /1/ exists at the matching size
    # (duration=100s × 128kbps / 8 = 1_600_000 bytes).
    responses.add(
        responses.GET,
        re.compile(r"https://m\.wsj\.net/audio/20260608/x-x-x-x-x/1/.*"),
        body=b"\x00" * 8, status=206,
        adding_headers={"Content-Range": f"bytes 0-7/{100 * 128_000 // 8}",
                         "Content-Type": "audio/mpeg"},
    )
    out = get_headlines(via="graphql", audio_only=True, limit=5)
    assert len(out["articles"]) == 1
    assert out["articles"][0]["article_id"] == "WP-WSJ-0000000004"


@responses.activate
def test_headlines_graphql_alias_resolves_to_canonical(fake_env, monkeypatch):
    """Friendly --collection=most-popular should map to MOST-POP-WSJ-NO-OPN_1."""
    monkeypatch.setenv("WSJ_REQUEST_SPACING_MS", "100")
    captured = {}

    def gql_cb(request):
        captured["url"] = request.url
        return (200, {}, '{"data":{"summaryCollectionContent":'
                          '{"id":"X","collectionItems":[]}}}')

    responses.add_callback(
        responses.GET,
        re.compile(r"https://shared-data\.dowjones\.io/gateway/graphql.*"),
        callback=gql_cb,
    )
    out = get_headlines(via="graphql", collection="most-popular", limit=5)
    assert "MOST-POP-WSJ-NO-OPN_1" in captured["url"]
    assert out["collection_id"] == "MOST-POP-WSJ-NO-OPN_1"
    assert out["articles"] == []


@responses.activate
def test_headlines_graphql_sends_cookie(monkeypatch, tmp_path):
    """GraphQL transport now requires and sends WSJ_COOKIE."""
    monkeypatch.setenv("WSJ_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("WSJ_COOKIE", "session_token=abc")
    monkeypatch.setenv("WSJ_REQUEST_SPACING_MS", "100")
    responses.add(
        responses.GET,
        re.compile(r"https://shared-data\.dowjones\.io/gateway/graphql.*"),
        json=_graphql_payload([]),
        status=200,
    )
    out = get_headlines(via="graphql")
    assert out["via"] == "graphql"
    assert out["articles"] == []
