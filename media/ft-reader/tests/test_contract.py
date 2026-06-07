"""Validate command outputs against schemas/*.json."""
import json
import re
from pathlib import Path

import responses
from jsonschema import validate

from ft_reader.article import get_article
from ft_reader.audio import get_audio
from ft_reader.headlines import get_headlines, STRUCTURE_URL
from ft_reader.myft import get_myft

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"


def _schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text())


@responses.activate
def test_headlines_matches_schema(fake_env, fx):
    responses.add(responses.GET, STRUCTURE_URL, json=fx("structure.json"), status=200)
    responses.add(
        responses.GET,
        re.compile(r"https://app-api\.ft\.com/__content/v4/article/.+"),
        json=fx("article.json"), status=200,
    )
    out = get_headlines(limit=2)
    validate(instance=out, schema=_schema("headlines.schema.json"))


@responses.activate
def test_article_matches_schema(fake_env, fx):
    uuid = "11111111-1111-1111-1111-111111111111"
    responses.add(
        responses.GET,
        re.compile(r"https://app-api\.ft\.com/__content/v4/article/.+"),
        json=fx("article.json"), status=200,
    )
    out = {"schema_version": 1, **get_article(uuid)}
    validate(instance=out, schema=_schema("article.schema.json"))


@responses.activate
def test_audio_matches_schema(fake_env):
    uuid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    responses.add(
        responses.GET,
        f"https://audio-available.ft.com/check/{uuid}",
        json={"haveFile": False}, status=200,
    )
    out = {"schema_version": 1, **get_audio(uuid)}
    validate(instance=out, schema=_schema("audio.schema.json"))


@responses.activate
def test_myft_matches_schema(fake_env, fx):
    responses.add(
        responses.GET,
        "https://app-api.ft.com/myft/content/v1?limit=50",
        json=fx("myft.json"), status=200, match_querystring=False,
    )
    out = get_myft()
    validate(instance=out, schema=_schema("myft.schema.json"))
