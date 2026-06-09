import re

import pytest
import responses

from wsj_reader.audio import get_audio
from wsj_reader.client import NotFoundError


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
    out = get_audio(article_url, download=False)
    assert out["article_id"] == "WP-WSJ-0000000001"
    assert out["available"] is True
    assert out["duration"] == 300
    # URL pattern: m.wsj.net/audio/{YYYYMMDD}/{uuid}/1/ele-{id}-full.mp3
    assert out["remote_url"] == (
        "https://m.wsj.net/audio/20260608/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/"
        "1/ele-wp-wsj-0000000001-full.mp3"
    )


@responses.activate
def test_audio_resolves_from_bare_article_id(fake_env, fx):
    """Passing a WP-WSJ-* id skips the article-page fetch entirely."""
    responses.add(
        responses.GET,
        re.compile(r"https://video-api\.shdsvc\.dowjones\.io/.*"),
        json=fx("read_to_me.json"), status=200,
    )
    out = get_audio("WP-WSJ-0000000001", download=False)
    assert out["available"] is True
    assert out["remote_url"].endswith("ele-wp-wsj-0000000001-full.mp3")


@responses.activate
def test_audio_download_writes_to_cache(fake_env, fx, tmp_cache_dir):
    article_url = "https://www.wsj.com/finance/test-article-one-aaaa1111"
    mp3_url = (
        "https://m.wsj.net/audio/20260608/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/"
        "1/ele-wp-wsj-0000000001-full.mp3"
    )
    responses.add(responses.GET, article_url, body=fx("article_page.html"),
                  status=200, content_type="text/html")
    responses.add(
        responses.GET,
        re.compile(r"https://video-api\.shdsvc\.dowjones\.io/.*"),
        json=fx("read_to_me.json"), status=200,
    )
    responses.add(responses.GET, mp3_url, body=b"ID3\x03\x00", status=200,
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
