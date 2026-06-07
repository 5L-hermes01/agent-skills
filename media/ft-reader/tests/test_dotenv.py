"""Confirm .env loading only touches skill dir + CWD, never walks up."""
import os
import subprocess
import sys
import textwrap
from pathlib import Path


def test_does_not_walk_up_from_module(tmp_path, monkeypatch):
    # Plant a malicious .env at a parent that the OLD code would have found.
    # New code must NOT load it.
    bogus_parent = tmp_path / "outer"
    bogus_parent.mkdir()
    (bogus_parent / ".env").write_text("FT_COOKIE=POISON\n")

    # Run a child python from a CWD inside that tree, with NO env vars set,
    # and verify FT_COOKIE doesn't end up populated.
    inner = bogus_parent / "inner"
    inner.mkdir()
    code = textwrap.dedent("""
        import os, sys
        sys.path.insert(0, %r)
        from ft_reader.client import _load_dotenv
        _load_dotenv()
        print('FT_COOKIE=' + os.environ.get('FT_COOKIE', '<unset>'))
    """ % str(Path(__file__).resolve().parent.parent / "src"))

    env = {k: v for k, v in os.environ.items()
           if k not in ("FT_COOKIE", "FT_SESSION_S", "FT_CLIENT_SESSION_ID",
                        "FT_APP_USER", "FT_CSRF")}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(inner), env=env, capture_output=True, text=True,
    )
    assert "POISON" not in result.stdout, f"_load_dotenv walked up and loaded the poison .env: {result.stdout}"


def test_loads_from_cwd_when_present(tmp_path):
    (tmp_path / ".env").write_text("FT_COOKIE=cwd-loaded\n")
    code = textwrap.dedent("""
        import os, sys
        sys.path.insert(0, %r)
        from ft_reader.client import _load_dotenv
        _load_dotenv()
        print(os.environ.get('FT_COOKIE', '<unset>'))
    """ % str(Path(__file__).resolve().parent.parent / "src"))
    env = {k: v for k, v in os.environ.items()
           if k not in ("FT_COOKIE", "FT_SESSION_S", "FT_CLIENT_SESSION_ID",
                        "FT_APP_USER", "FT_CSRF")}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(tmp_path), env=env, capture_output=True, text=True,
    )
    assert "cwd-loaded" in result.stdout
