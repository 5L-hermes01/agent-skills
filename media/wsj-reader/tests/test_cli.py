import json

import pytest
import responses

from wsj_reader.client import UpstreamError
from wsj_reader.cli import main


@responses.activate
def test_headlines_cli_defaults_to_homepage_without_cookie(monkeypatch, tmp_path, fx, capsys):
    monkeypatch.setenv("WSJ_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("WSJ_COOKIE", raising=False)
    responses.add(
        responses.GET,
        "https://www.wsj.com/",
        body=fx("homepage.html"),
        status=200,
        content_type="text/html",
    )

    rc = main(["headlines", "--limit", "1", "--no-cache"])

    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["via"] == "homepage"
    assert payload["articles"][0]["headline"] == "Synthetic homepage lead story"
    assert "Cookie" not in responses.calls[0].request.headers


def test_headlines_cli_rejects_collection_without_graphql(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["headlines", "--collection", "most-popular"])

    captured = capsys.readouterr()
    assert exc.value.code == 2
    assert "--collection requires --via=graphql" in captured.err


def test_headlines_cli_rejects_homepage_audio_only(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["headlines", "--audio-only"])

    captured = capsys.readouterr()
    assert exc.value.code == 2
    assert "--audio-only requires --via=graphql" in captured.err


def test_refresh_cookie_cli_invokes_browser_helper(monkeypatch, capsys):
    captured_args = {}

    def fake_refresh(**kwargs):
        captured_args.update(kwargs)
        return {"wrote": False, "cookie_count": 2, "ok": True}

    monkeypatch.setattr("wsj_reader.cli.refresh_cookie_with_browser", fake_refresh)

    rc = main([
        "refresh-cookie",
        "https://www.wsj.com/finance/test",
        "--profile-dir",
        "/tmp/wsj-profile",
        "--headless",
        "--timeout",
        "3",
        "--dry-run",
    ])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == 0
    assert payload["schema_version"] == 1
    assert payload["wrote"] is False
    assert payload["cookie_count"] == 2
    assert captured_args == {
        "url": "https://www.wsj.com/finance/test",
        "profile_dir": "/tmp/wsj-profile",
        "headless": True,
        "timeout_s": 3,
        "write": False,
    }


def test_refresh_cookie_cli_accepts_trailing_json_errors(monkeypatch, capsys):
    def fake_refresh(**_kwargs):
        return {"wrote": False, "cookie_count": 2}

    monkeypatch.setattr("wsj_reader.cli.refresh_cookie_with_browser", fake_refresh)

    rc = main(["refresh-cookie", "--dry-run", "--json-errors"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == 0
    assert payload["schema_version"] == 1
    assert payload["wrote"] is False


def test_refresh_cookie_cli_accepts_global_json_errors(monkeypatch, capsys):
    def fake_refresh(**_kwargs):
        raise UpstreamError("browser missing")

    monkeypatch.setattr("wsj_reader.cli.refresh_cookie_with_browser", fake_refresh)

    rc = main(["--json-errors", "refresh-cookie", "--dry-run"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == 4
    assert payload == {"error": {"code": "NETWORK", "message": "browser missing"}}
