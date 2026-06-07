import sys
from pathlib import Path

# Add scripts/ to sys.path so we can import set_cookie as a module.
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import set_cookie as sc  # noqa: E402


def test_parses_raw_cookie_header():
    raw = "FTSession_s=abc; FTClientSessionId=def; AppUser=ghi; _csrf=jkl; _ga=ignored"
    out = sc.parse(raw)
    assert out["FTSession_s"] == "abc"
    assert out["_csrf"] == "jkl"
    assert out["_ga"] == "ignored"


def test_parses_with_cookie_header_label():
    raw = "Cookie: FTSession_s=abc; AppUser=ghi"
    out = sc.parse(raw)
    assert out["FTSession_s"] == "abc"
    assert out["AppUser"] == "ghi"


def test_parses_set_cookie_multiline():
    raw = """set-cookie: FTSession_s=abc; Path=/; Secure
set-cookie: AppUser=ghi; HttpOnly"""
    out = sc.parse(raw)
    assert out == {"FTSession_s": "abc", "AppUser": "ghi"}


def test_parses_json_blob():
    raw = '{"FTSession_s": "abc", "AppUser": "ghi"}'
    out = sc.parse(raw)
    assert out == {"FTSession_s": "abc", "AppUser": "ghi"}


def test_update_env_writes_blob_and_named_vars(tmp_path):
    env = tmp_path / ".env"
    cookies = {"FTSession_s": "S", "FTClientSessionId": "C", "AppUser": "A",
               "_csrf": "X", "_ga": "ignored"}
    sc.update_env(env, cookies)
    text = env.read_text()
    assert "FT_COOKIE=FTSession_s=S; FTClientSessionId=C; AppUser=A; _csrf=X; _ga=ignored" in text
    assert "FT_SESSION_S=S" in text
    assert "FT_APP_USER=A" in text
    assert "FT_CSRF=X" in text


def test_update_env_preserves_other_lines(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FT_CACHE_DIR=/tmp/c\nFT_COOKIE=old\n")
    sc.update_env(env, {"FTSession_s": "new"})
    text = env.read_text()
    assert "FT_CACHE_DIR=/tmp/c" in text
    assert "FT_COOKIE=FTSession_s=new" in text
    assert "FT_COOKIE=old" not in text


def test_dry_run_does_not_write(tmp_path):
    env = tmp_path / ".env"
    sc.update_env(env, {"FTSession_s": "abc"}, dry_run=True)
    assert not env.exists()
