import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import set_cookie as sc  # noqa: E402


def test_parses_raw_cookie_header():
    raw = ("nyt-a=A; NYT-S=S; nyt-jkidd=J; nyt-purr=P; nyt-b-sid=B; _ga=ignored")
    out = sc.parse(raw)
    assert out["nyt-a"] == "A"
    assert out["NYT-S"] == "S"
    assert out["nyt-jkidd"] == "J"
    assert out["nyt-purr"] == "P"
    assert out["nyt-b-sid"] == "B"


def test_parses_with_cookie_label():
    raw = "Cookie: nyt-a=A; NYT-S=S"
    out = sc.parse(raw)
    assert out["nyt-a"] == "A"


def test_update_env_writes_named_vars(tmp_path):
    env = tmp_path / ".env"
    cookies = {"nyt-a": "A", "NYT-S": "S", "nyt-jkidd": "J",
               "nyt-purr": "P", "nyt-b-sid": "B"}
    sc.update_env(env, cookies)
    text = env.read_text()
    for k in ("NYT_A=A", "NYT_S=S", "NYT_JKIDD=J", "NYT_PURR=P", "NYT_B_SID=B"):
        assert k in text


def test_update_env_preserves_other_lines(tmp_path):
    env = tmp_path / ".env"
    env.write_text("NYT_CACHE_DIR=/tmp/c\nNYT_A=old\n")
    sc.update_env(env, {"nyt-a": "new"})
    text = env.read_text()
    assert "NYT_CACHE_DIR=/tmp/c" in text
    assert "NYT_A=new" in text
    assert "NYT_A=old" not in text


def test_dry_run_does_not_write(tmp_path):
    env = tmp_path / ".env"
    sc.update_env(env, {"nyt-a": "abc"}, dry_run=True)
    assert not env.exists()
