"""Validate command outputs against schemas/*.json."""
import json
import re
from pathlib import Path

import responses
from jsonschema import validate

from nyt_reader.article import get_article
from nyt_reader.audio import get_audio
from nyt_reader.headlines import get_headlines
from nyt_reader.saved import get_saved

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"


def _schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text())


@responses.activate
def test_headlines_matches_schema(fake_env, fx):
    responses.add(
        responses.GET,
        re.compile(r"https://samizdat-graphql\.nytimes\.com/graphql/v2.*"),
        json=fx("headlines.json"), status=200,
    )
    validate(instance=get_headlines(limit=5), schema=_schema("headlines.schema.json"))


@responses.activate
def test_article_matches_schema(fake_env, fx):
    url = "https://www.nytimes.com/2026/01/01/test/sample-story-one.html"
    responses.add(responses.GET, url, body=fx("article_page.html"), status=200,
                  content_type="text/html")
    out = {"schema_version": 1, **get_article(url)}
    validate(instance=out, schema=_schema("article.schema.json"))


@responses.activate
def test_audio_matches_schema(fake_env, fx):
    url = "https://www.nytimes.com/2026/01/01/test/sample-story-one.html"
    responses.add(responses.GET, url, body=fx("article_page.html"), status=200,
                  content_type="text/html")
    out = {"schema_version": 1, **get_audio(url)}
    validate(instance=out, schema=_schema("audio.schema.json"))


def test_saved_empty_matches_schema(fake_env):
    out = get_saved(None)
    validate(instance=out, schema=_schema("saved.schema.json"))
