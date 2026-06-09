"""Validate command outputs against schemas/*.json."""
import json
import re
from pathlib import Path

import responses
from jsonschema import validate

from wsj_reader.article import get_article
from wsj_reader.audio import get_audio
from wsj_reader.headlines import get_headlines

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"


def _schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text())


@responses.activate
def test_headlines_matches_schema(fake_env, fx):
    responses.add(responses.GET,
                  re.compile(r"https://www\.wsj\.com/print-edition/.*"),
                  body=fx("print_edition.html"),
                  status=200, content_type="text/html")
    out = get_headlines(edition_date="20260608")
    validate(instance=out, schema=_schema("headlines.schema.json"))


@responses.activate
def test_article_matches_schema(fake_env, fx):
    url = "https://www.wsj.com/finance/test-article-one-aaaa1111"
    responses.add(responses.GET, url, body=fx("article_page.html"),
                  status=200, content_type="text/html")
    out = {"schema_version": 1, **get_article(url)}
    validate(instance=out, schema=_schema("article.schema.json"))


@responses.activate
def test_audio_matches_schema(fake_env, fx):
    responses.add(
        responses.GET,
        re.compile(r"https://video-api\.shdsvc\.dowjones\.io/.*"),
        json=fx("read_to_me.json"), status=200,
    )
    out = {"schema_version": 1, **get_audio("WP-WSJ-0000000001")}
    validate(instance=out, schema=_schema("audio.schema.json"))
