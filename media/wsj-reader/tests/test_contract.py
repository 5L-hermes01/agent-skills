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
def test_headlines_html_matches_schema(fake_env, fx):
    responses.add(responses.GET,
                  re.compile(r"https://www\.wsj\.com/print-edition/.*"),
                  body=fx("print_edition.html"),
                  status=200, content_type="text/html")
    out = get_headlines(via="html", edition_date="20260608")
    validate(instance=out, schema=_schema("headlines.schema.json"))


@responses.activate
def test_headlines_graphql_matches_schema(fake_env, monkeypatch):
    monkeypatch.setenv("WSJ_REQUEST_SPACING_MS", "100")
    responses.add(
        responses.GET,
        re.compile(r"https://shared-data\.dowjones\.io/gateway/graphql.*"),
        json={"data": {"summaryCollectionContent": {
            "id": "MOST-POP-WSJ-NO-OPN_1",
            "collectionItems": [{
                "id": "WP-WSJ-0000000099",
                "content": {
                    "sectionName": "World",
                    "breakingNews": False,
                    "sourceUrl": "https://www.wsj.com/world/x",
                    "publishedDateTimeUtc": "2026-06-08T00:00:00Z",
                    "flattenedSummary": {
                        "headline": {"text": "Synthetic schema test headline"},
                        "flashline": None,
                        "image": [{"src": {"baseUrl": "https://images.wsj.net/",
                                            "path": "im-99"}}],
                    },
                    "mobileSummary": {
                        "description": {"content": {"text": "Short."}},
                    },
                },
            }],
        }}},
        status=200,
    )
    responses.add(
        responses.GET,
        re.compile(r"https://video-api\.shdsvc\.dowjones\.io/.*"),
        json={"items": [{
            "id": "{ABCDEF00-1111-2222-3333-444444444444}",
            "duration": "120",
            "formattedCreationDate": "6/8/2026 5:00:00 PM",
            "author": "Reporter",
        }]},
        status=200,
    )
    out = get_headlines()
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
