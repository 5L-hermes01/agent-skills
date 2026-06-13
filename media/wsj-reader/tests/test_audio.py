import re

import pytest
import responses

from wsj_reader.audio import get_audio
from wsj_reader.client import NotFoundError


# ─── helpers ─────────────────────────────────────────────────────────────


def _mock_cdn_probe(url: str, *, total_bytes: int):
    """Mock a Range request returning HTTP 206 with the right Content-Range."""
    responses.add(
        responses.GET, url, body=b"\x00" * 8, status=206,
        adding_headers={
            "Content-Range": f"bytes 0-7/{total_bytes}",
            "Content-Type": "audio/mpeg",
        },
    )


def _mock_cdn_403(url: str):
    responses.add(responses.GET, url, body=b"", status=403)


# Canonical fixture-derived MP3 URL for read_to_me.json.
# duration=300s at 128kbps mono = 4,800,000 bytes.
CANONICAL_URL = (
    "https://m.wsj.net/audio/20260608/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/"
    "1/ele-wp-wsj-0000000001-full.mp3"
)
CANONICAL_TOTAL = 300 * 128_000 // 8  # = 4_800_000


# ─── tests ───────────────────────────────────────────────────────────────


@responses.activate
def test_audio_resolves_from_article_url(fake_env, fx):
    article_url = "https://www.wsj.com/finance/test-article-one-aaaa1111"
    responses.add(responses.GET, article_url, body=fx("article_page.html"),
                  status=200, content_type="text/html")
    responses.add(
        responses.GET,
        re.compile(r"https://video-api\.shdsvc\.dowjones\.io/api/legacy/find-all-videos.*"),
        json=fx("read_to_me.json"), status=200,
    )
    _mock_cdn_probe(CANONICAL_URL, total_bytes=CANONICAL_TOTAL)

    out = get_audio(article_url, download=False)
    assert out["article_id"] == "WP-WSJ-0000000001"
    assert out["available"] is True
    assert out["duration"] == 300
    assert out["remote_url"] == CANONICAL_URL


@responses.activate
def test_audio_resolves_from_bare_article_id(fake_env, fx):
    """Passing a WP-WSJ-* id skips the article-page fetch entirely."""
    responses.add(
        responses.GET,
        re.compile(r"https://video-api\.shdsvc\.dowjones\.io/.*"),
        json=fx("read_to_me.json"), status=200,
    )
    _mock_cdn_probe(CANONICAL_URL, total_bytes=CANONICAL_TOTAL)

    out = get_audio("WP-WSJ-0000000001", download=False)
    assert out["available"] is True
    assert out["remote_url"].endswith("ele-wp-wsj-0000000001-full.mp3")


@responses.activate
def test_audio_download_writes_to_cache(fake_env, fx, tmp_cache_dir):
    article_url = "https://www.wsj.com/finance/test-article-one-aaaa1111"
    responses.add(responses.GET, article_url, body=fx("article_page.html"),
                  status=200, content_type="text/html")
    responses.add(
        responses.GET,
        re.compile(r"https://video-api\.shdsvc\.dowjones\.io/.*"),
        json=fx("read_to_me.json"), status=200,
    )
    _mock_cdn_probe(CANONICAL_URL, total_bytes=CANONICAL_TOTAL)
    # The download itself.
    responses.add(responses.GET, CANONICAL_URL, body=b"ID3\x03\x00", status=200,
                  content_type="audio/mpeg")
    out = get_audio(article_url, download=True)
    assert out["local_path"]
    assert open(out["local_path"], "rb").read().startswith(b"ID3")


@responses.activate
def test_audio_not_available_when_items_empty(fake_env):
    responses.add(
        responses.GET,
        re.compile(r"https://video-api\.shdsvc\.dowjones\.io/.*"),
        json={"items": []}, status=200,
    )
    out = get_audio("WP-WSJ-0000000999")
    assert out["available"] is False
    assert out["remote_url"] is None


def test_audio_rejects_bad_ref(fake_env):
    with pytest.raises(NotFoundError):
        get_audio("not-a-url-or-id")


# ─── New: probe-related behavior ─────────────────────────────────────────


@responses.activate
def test_audio_probe_walks_segments_until_size_matches(fake_env, fx):
    """Segment /1/ is a partial render; /2/ is canonical. Probe picks /2/."""
    responses.add(
        responses.GET,
        re.compile(r"https://video-api\.shdsvc\.dowjones\.io/.*"),
        json=fx("read_to_me.json"), status=200,
    )
    base = "https://m.wsj.net/audio/20260608/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    slug = "ele-wp-wsj-0000000001-full"
    # /1/ exists but is short (~30s — below the 10% tolerance from 300s).
    _mock_cdn_probe(f"{base}/1/{slug}.mp3", total_bytes=480_000)
    # /2/ is the canonical full render at 300s.
    _mock_cdn_probe(f"{base}/2/{slug}.mp3", total_bytes=CANONICAL_TOTAL)

    out = get_audio("WP-WSJ-0000000001", download=False)
    assert out["available"] is True
    assert out["remote_url"] == f"{base}/2/{slug}.mp3"


@responses.activate
def test_audio_probe_uses_date_plus_one_when_today_is_empty(fake_env, fx):
    """Articles published evening UTC have audio at pub_date+1."""
    responses.add(
        responses.GET,
        re.compile(r"https://video-api\.shdsvc\.dowjones\.io/.*"),
        json=fx("read_to_me.json"), status=200,
    )
    uuid_path = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    slug = "ele-wp-wsj-0000000001-full"
    # First date (pub_date = 20260608): every segment 403.
    for seg in range(1, 17):
        _mock_cdn_403(f"https://m.wsj.net/audio/20260608/{uuid_path}/{seg}/{slug}.mp3")
    # Second date (pub_date + 1 = 20260609): /1/ matches.
    _mock_cdn_probe(
        f"https://m.wsj.net/audio/20260609/{uuid_path}/1/{slug}.mp3",
        total_bytes=CANONICAL_TOTAL,
    )

    out = get_audio("WP-WSJ-0000000001", download=False)
    assert out["available"] is True
    assert "/20260609/" in out["remote_url"]


@responses.activate
def test_audio_probe_returns_unavailable_when_no_variant_exists(fake_env, fx):
    """All probed (date, seg) pairs 403 → available=False."""
    responses.add(
        responses.GET,
        re.compile(r"https://video-api\.shdsvc\.dowjones\.io/.*"),
        json=fx("read_to_me.json"), status=200,
    )
    # Catch-all 403 for any CDN probe.
    responses.add(
        responses.GET,
        re.compile(r"https://m\.wsj\.net/audio/.*"),
        body=b"", status=403,
    )
    out = get_audio("WP-WSJ-0000000001", download=False)
    assert out["available"] is False
    assert out["remote_url"] is None


@responses.activate
def test_audio_probe_caches_result(fake_env, fx, tmp_cache_dir):
    """Second resolve for the same article uses the cached probe result."""
    responses.add(
        responses.GET,
        re.compile(r"https://video-api\.shdsvc\.dowjones\.io/.*"),
        json=fx("read_to_me.json"), status=200,
    )
    _mock_cdn_probe(CANONICAL_URL, total_bytes=CANONICAL_TOTAL)

    out1 = get_audio("WP-WSJ-0000000001", download=False)
    # Snapshot calls so far, then resolve again.
    n_before = len(responses.calls)
    out2 = get_audio("WP-WSJ-0000000001", download=False)
    n_after = len(responses.calls)

    assert out1["remote_url"] == out2["remote_url"]
    # Zero new CDN probes on the second call.
    assert n_after == n_before
