import re

import pytest
import responses

from nyt_reader.article import get_article
from nyt_reader.client import NotFoundError


@responses.activate
def test_article_extracts_next_data(fake_env, fx):
    url = "https://www.nytimes.com/2026/01/01/test/sample-story-one.html"
    responses.add(responses.GET, url, body=fx("article_page.html"), status=200,
                  content_type="text/html")
    out = get_article(url)
    assert out["title"] == "Synthetic test article body"
    assert out["byline"] == "By Test Author"
    assert out["section"] == "Test Section"
    assert out["audio_url"].endswith(".mp3")
    assert out["audio_duration"] == 300
    assert isinstance(out["body"], dict)


def test_article_rejects_uri(fake_env):
    with pytest.raises(NotFoundError):
        get_article("nyt://article/abc")


@responses.activate
def test_article_handles_missing_next_data(fake_env):
    url = "https://www.nytimes.com/2026/01/01/no-blob.html"
    responses.add(responses.GET, url, body="<html><body>no blob here</body></html>",
                  status=200, content_type="text/html")
    with pytest.raises(NotFoundError):
        get_article(url)
