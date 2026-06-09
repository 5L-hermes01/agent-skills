import re

import responses

from nyt_reader.headlines import get_headlines


@responses.activate
def test_headlines_walks_personalized_homes(fake_env, fx):
    responses.add(
        responses.GET,
        re.compile(r"https://samizdat-graphql\.nytimes\.com/graphql/v2.*LegacyPersonalizedPackagesQuery.*"),
        json=fx("headlines.json"),
        status=200,
    )
    out = get_headlines(limit=10)

    assert out["schema_version"] == 1
    assert "fetched_at" in out
    titles = [a["title"] for a in out["articles"]]
    assert titles == [
        "Synthetic test headline one",
        "Synthetic test headline two (no audio)",
    ]
    first = out["articles"][0]
    assert first["audio_url"].endswith("/article-11111111-1111-1111-1111-111111111111-job-1.mp3")
    assert first["audio_duration"] == 300
    assert first["byline"] == "By Test Author"
    assert first["section"] == "Test Section"


@responses.activate
def test_headlines_audio_only_filters(fake_env, fx):
    responses.add(
        responses.GET,
        re.compile(r"https://samizdat-graphql\.nytimes\.com/graphql/v2.*"),
        json=fx("headlines.json"),
        status=200,
    )
    out = get_headlines(limit=10, audio_only=True)
    assert len(out["articles"]) == 1
    assert out["articles"][0]["audio_url"] is not None


@responses.activate
def test_headlines_dedupes_by_uri(fake_env, fx):
    # Duplicate the first asset inside personalizedData; expect dedup to keep one.
    payload = fx("headlines.json")
    payload["data"]["personalizationHomes"][0]["personalizedData"].append(
        payload["data"]["personalizationHomes"][0]["personalizedData"][0]
    )
    responses.add(
        responses.GET,
        re.compile(r"https://samizdat-graphql\.nytimes\.com/graphql/v2.*"),
        json=payload, status=200,
    )
    out = get_headlines(limit=10)
    uris = [a["uri"] for a in out["articles"]]
    assert len(uris) == len(set(uris))
