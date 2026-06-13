import re

import responses

from nyt_reader.audio import get_audio


@responses.activate
def test_audio_check_only_from_html(fake_env, fx):
    url = "https://www.nytimes.com/2026/01/01/test/sample-story-one.html"
    responses.add(responses.GET, url, body=fx("article_page.html"), status=200,
                  content_type="text/html")
    out = get_audio(url, download=False)
    assert out["available"] is True
    assert out["remote_url"].endswith(".mp3")
    assert out["local_path"] is None


@responses.activate
def test_audio_download_writes_to_cache(fake_env, fx, tmp_cache_dir):
    url = "https://www.nytimes.com/2026/01/01/test/sample-story-one.html"
    mp3 = "https://static.nytimes.com/narrated-articles/synthetic/article-11111111-1111-1111-1111-111111111111/job-1/article-11111111-1111-1111-1111-111111111111-job-1.mp3"
    responses.add(responses.GET, url, body=fx("article_page.html"), status=200,
                  content_type="text/html")
    responses.add(responses.GET, mp3, body=b"ID3\x03\x00", status=200,
                  content_type="audio/mpeg")
    out = get_audio(url, download=True)
    assert out["local_path"]
    assert open(out["local_path"], "rb").read().startswith(b"ID3")


@responses.activate
def test_audio_not_available_when_html_lacks_audio(fake_env):
    url = "https://www.nytimes.com/2026/01/01/no-audio.html"
    html = (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"article":{"__typename":"Article",'
        '"headline":{"default":"no audio"},"firstPublished":"x"}}}}'
        '</script></body></html>'
    )
    responses.add(responses.GET, url, body=html, status=200, content_type="text/html")
    out = get_audio(url, download=True)
    assert out["available"] is False
    assert out["local_path"] is None
