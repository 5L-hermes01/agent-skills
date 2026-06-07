import responses

from ft_reader.myft import get_myft


@responses.activate
def test_myft_list_shape(fake_env, fx):
    responses.add(
        responses.GET,
        "https://app-api.ft.com/myft/content/v1?limit=50",
        json=fx("myft.json"),
        status=200,
        match_querystring=False,
    )
    out = get_myft(limit=50)
    assert out["schema_version"] == 1
    assert out["count"] == 2
    a, b = out["items"]
    assert a["title"] == "Synthetic saved article one"
    assert a["audio_available"] is True
    assert a["audio_duration"] == "05:00"
    assert b["audio_available"] is False


@responses.activate
def test_myft_download_audio(fake_env, fx):
    items = fx("myft.json")
    responses.add(
        responses.GET,
        "https://app-api.ft.com/myft/content/v1?limit=50",
        json=items, status=200, match_querystring=False,
    )
    responses.add(
        responses.GET,
        items[0]["audio"]["url"],
        body=b"ID3\x03\x00",
        status=200,
    )
    out = get_myft(limit=50, download_audio=True)
    assert out["items"][0]["audio_local_path"] is not None
    assert out["items"][1]["audio_local_path"] is None
