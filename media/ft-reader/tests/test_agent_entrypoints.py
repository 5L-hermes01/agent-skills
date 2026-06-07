"""All three agent entrypoint files must exist and reference the four commands."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMANDS = ("headlines", "article", "audio", "myft")


def _read(name: str) -> str:
    p = ROOT / name
    assert p.is_file(), f"{name} missing"
    return p.read_text()


def test_skill_md_documents_all_commands():
    text = _read("SKILL.md")
    for cmd in COMMANDS:
        assert f"ft {cmd}" in text, f"SKILL.md missing 'ft {cmd}'"


def test_agents_md_documents_all_commands():
    text = _read("AGENTS.md")
    for cmd in COMMANDS:
        assert f"ft {cmd}" in text, f"AGENTS.md missing 'ft {cmd}'"


def test_gemini_md_documents_all_commands():
    text = _read("GEMINI.md")
    for cmd in COMMANDS:
        assert f"ft {cmd}" in text, f"GEMINI.md missing 'ft {cmd}'"


def test_env_sample_lists_required_cookies():
    text = _read(".env.sample")
    # FT_COOKIE is the primary; the four legacy names should still be documented as fallback.
    for key in ("FT_COOKIE", "FT_SESSION_S", "FT_CLIENT_SESSION_ID", "FT_APP_USER", "FT_CSRF"):
        assert key in text, f".env.sample missing {key}"
