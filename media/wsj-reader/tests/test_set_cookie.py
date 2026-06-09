import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import set_cookie as sc  # noqa: E402


def test_parses_raw_cookie_header():
    raw = "DJSESSION=abc; djcs_route=def; AMCV_xxx=ghi; usr_prof_v2=jkl"
    out = sc.parse(raw)
    assert "DJSESSION=abc" in out
    assert "AMCV_xxx=ghi" in out


def test_parses_with_label():
    raw = "Cookie: DJSESSION=abc; djcs_route=def"
    out = sc.parse(raw)
    assert out == "DJSESSION=abc; djcs_route=def"


def test_update_env_writes_cookie(tmp_path):
    env = tmp_path / ".env"
    sc.update_env(env, "DJSESSION=abc; djcs_route=def; many=values")
    text = env.read_text()
    assert "WSJ_COOKIE=DJSESSION=abc; djcs_route=def; many=values" in text


def test_update_env_preserves_other_lines(tmp_path):
    env = tmp_path / ".env"
    env.write_text("WSJ_CACHE_DIR=/tmp/c\nWSJ_COOKIE=old\n")
    sc.update_env(env, "new=value")
    text = env.read_text()
    assert "WSJ_CACHE_DIR=/tmp/c" in text
    assert "WSJ_COOKIE=new=value" in text
    assert "WSJ_COOKIE=old" not in text


def test_dry_run_does_not_write(tmp_path):
    env = tmp_path / ".env"
    sc.update_env(env, "test=value", dry_run=True)
    assert not env.exists()
