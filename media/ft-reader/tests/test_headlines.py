import re

import responses

from ft_reader.headlines import get_headlines, STRUCTURE_URL


@responses.activate
def test_headlines_parses_structure_and_hydrates(fake_env, fx):
    structure = fx("structure.json")
    article = fx("article.json")
    responses.add(responses.GET, STRUCTURE_URL, json=structure, status=200)
    # Any UUID article request returns the same fixture (with id rewritten in normalize).
    responses.add(
        responses.GET,
        re.compile(r"https://app-api\.ft\.com/__content/v4/article/.+"),
        json=article,
        status=200,
    )

    out = get_headlines(limit=2)

    assert out["schema_version"] == 1
    assert "fetched_at" in out
    section_ids = [s["id"] for s in out["sections"]]
    assert section_ids == ["home", "world", "tech"]

    home = next(s for s in out["sections"] if s["id"] == "home")
    assert home["name"] == "Home"
    assert len(home["headlines"]) == 2
    assert all("title" in h for h in home["headlines"])
    assert all(h["title"] == "Lorem ipsum sample headline" for h in home["headlines"])

    tech = next(s for s in out["sections"] if s["id"] == "tech")
    assert len(tech["headlines"]) == 2  # section-shape slots (teasers directly on slot)


@responses.activate
def test_headlines_section_filter(fake_env, fx):
    responses.add(responses.GET, STRUCTURE_URL, json=fx("structure.json"), status=200)
    responses.add(
        responses.GET,
        re.compile(r"https://app-api\.ft\.com/__content/v4/article/.+"),
        json=fx("article.json"),
        status=200,
    )
    out = get_headlines(section="world", limit=5)
    assert [s["id"] for s in out["sections"]] == ["world"]


@responses.activate
def test_per_article_error_does_not_abort(fake_env, fx):
    structure = fx("structure.json")
    responses.add(responses.GET, STRUCTURE_URL, json=structure, status=200)
    # First two UUIDs 200, the third one 500.
    responses.add(
        responses.GET,
        re.compile(r"https://app-api\.ft\.com/__content/v4/article/1+.*"),
        json=fx("article.json"), status=200,
    )
    responses.add(
        responses.GET,
        re.compile(r"https://app-api\.ft\.com/__content/v4/article/2+.*"),
        json=fx("article.json"), status=200,
    )
    responses.add(
        responses.GET,
        re.compile(r"https://app-api\.ft\.com/__content/v4/article/3+.*"),
        body="boom", status=500,
    )
    out = get_headlines(section="home", limit=5)
    headlines = out["sections"][0]["headlines"]
    assert any("error" in h for h in headlines)
    assert any(h.get("title") == "Lorem ipsum sample headline" for h in headlines)
