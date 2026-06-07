import responses

from ft_reader.audio import get_audio


@responses.activate
def test_audio_check_only(fake_env):
    uuid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    responses.add(
        responses.GET,
        f"https://audio-available.ft.com/check/{uuid}",
        json={
            "haveFile": True,
            "url": f"https://example.test/audio/{uuid}.mp3",
            "size": 12345,
            "duration": {"humantime": "05:00", "seconds": 300},
        },
        status=200,
    )
    out = get_audio(uuid, download=False)
    assert out["uuid"] == uuid
    assert out["available"] is True
    assert out["remote_url"].endswith(f"{uuid}.mp3")
    assert out["duration"] == "05:00"
    assert out["local_path"] is None


@responses.activate
def test_audio_download_writes_to_cache(fake_env, tmp_cache_dir):
    uuid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    remote = f"https://example.test/audio/{uuid}.mp3"
    responses.add(
        responses.GET,
        f"https://audio-available.ft.com/check/{uuid}",
        json={"haveFile": True, "url": remote, "size": 3, "duration": {"humantime": "00:01"}},
        status=200,
    )
    responses.add(responses.GET, remote, body=b"ID3\x03\x00", status=200)
    out = get_audio(uuid, download=True)
    assert out["local_path"]
    assert open(out["local_path"], "rb").read().startswith(b"ID3")


@responses.activate
def test_audio_not_available(fake_env):
    uuid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    responses.add(
        responses.GET,
        f"https://audio-available.ft.com/check/{uuid}",
        json={"haveFile": False},
        status=200,
    )
    out = get_audio(uuid, download=True)
    assert out["available"] is False
    assert out["local_path"] is None
