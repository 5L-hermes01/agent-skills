import sys

import pytest

from wsj_reader.client import SessionExpiredError, UpstreamError
from wsj_reader.cookie_refresh import (
    _article_unlock_status,
    _cookie_header_from_playwright,
    _is_browser_install_error,
    _ready_to_write,
    _update_env_cookie,
    refresh_cookie_with_browser,
)


def test_cookie_header_from_playwright_filters_to_wsj_domains():
    cookies = [
        {"name": "datadome", "value": "edge", "domain": ".wsj.com"},
        {"name": "ca_id", "value": "unlock", "domain": "www.wsj.com"},
        {"name": "other", "value": "ignored", "domain": "example.com"},
    ]

    assert _cookie_header_from_playwright(cookies) == "datadome=edge; ca_id=unlock"


def test_update_env_cookie_replaces_existing_value(tmp_path):
    env = tmp_path / ".env"
    env.write_text("WSJ_CACHE_DIR=/tmp/wsj\nWSJ_COOKIE = old=value\n")

    _update_env_cookie(env, "datadome=edge; ca_id=unlock")

    assert env.read_text() == "WSJ_CACHE_DIR=/tmp/wsj\nWSJ_COOKIE=datadome=edge; ca_id=unlock\n"
    assert oct(env.stat().st_mode & 0o777) == "0o600"


def test_ready_to_write_requires_edge_cookies_and_article_unlock():
    cookie = "datadome=edge; ca_id=unlock"

    assert _ready_to_write(cookie, {"article_page": False}) is True
    assert _ready_to_write(cookie, {
        "article_page": True,
        "ok": True,
        "snippet": False,
        "serverUnlocked": True,
        "paragraphs": 20,
    }) is True
    assert _ready_to_write("datadome=edge", {"article_page": False}) is False
    assert _ready_to_write("x-datadome=edge; ca_id=unlock", {"article_page": False}) is False
    assert _ready_to_write(cookie, {"article_page": True, "ok": False}) is False


def test_article_unlock_status_detects_tracking_meta_and_short_unlocked_body():
    class FakePage:
        def evaluate(self, _script):
            return {
                "article_page": True,
                "ok": True,
                "snippet": False,
                "serverUnlocked": True,
                "paragraphs": 1,
                "body_blocks": 1,
                "article_id": "WP-WSJ-123",
            }

    status = _article_unlock_status(FakePage())

    assert status["article_page"] is True
    assert status["ok"] is True
    assert status["article_id"] == "WP-WSJ-123"


def test_playwright_install_error_detection_matches_missing_browser_message():
    err = Exception("Executable doesn't exist at /chromium. Please run the following command to download new browsers: playwright install")

    assert _is_browser_install_error(err) is True


def test_refresh_cookie_missing_playwright_reports_install(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "playwright", None)

    with pytest.raises(UpstreamError, match=r"Playwright Chromium is not installed"):
        refresh_cookie_with_browser(env_path=tmp_path / ".env", timeout_s=1)


def test_refresh_cookie_translates_navigation_timeout(monkeypatch, tmp_path):
    class FakeTimeoutError(Exception):
        pass

    class FakePage:
        def goto(self, *_args, **_kwargs):
            raise FakeTimeoutError("navigation timed out")

    class FakeContext:
        pages = [FakePage()]

        def close(self):
            pass

    class FakeChromium:
        def launch_persistent_context(self, *_args, **_kwargs):
            return FakeContext()

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class FakeModule:
        Error = Exception
        TimeoutError = FakeTimeoutError

        @staticmethod
        def sync_playwright():
            return FakePlaywright()

    monkeypatch.setitem(sys.modules, "playwright", object())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", FakeModule)

    with pytest.raises(SessionExpiredError, match=r"before timeout"):
        refresh_cookie_with_browser(env_path=tmp_path / ".env", timeout_s=1)


def test_refresh_cookie_translates_navigation_error(monkeypatch, tmp_path):
    class FakePlaywrightError(Exception):
        pass

    class FakeTimeoutError(Exception):
        pass

    class FakePage:
        def goto(self, *_args, **_kwargs):
            raise FakePlaywrightError("net::ERR_CONNECTION_RESET")

    class FakeContext:
        pages = [FakePage()]

        def close(self):
            pass

    class FakeChromium:
        def launch_persistent_context(self, *_args, **_kwargs):
            return FakeContext()

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class FakeModule:
        Error = FakePlaywrightError
        TimeoutError = FakeTimeoutError

        @staticmethod
        def sync_playwright():
            return FakePlaywright()

    monkeypatch.setitem(sys.modules, "playwright", object())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", FakeModule)

    with pytest.raises(UpstreamError, match=r"Unable to navigate Chromium"):
        refresh_cookie_with_browser(env_path=tmp_path / ".env", timeout_s=1)
