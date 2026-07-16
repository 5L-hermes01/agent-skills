"""Tests for the jargon skill."""
from __future__ import annotations

import json
import os
import re
import sys

SKILL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "research", "jargon")


def test_skill_md_exists():
    path = os.path.join(SKILL_DIR, "SKILL.md")
    assert os.path.exists(path)


def test_description_length():
    path = os.path.join(SKILL_DIR, "SKILL.md")
    with open(path) as f:
        content = f.read()
    match = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
    assert match, "description not found"
    desc = match.group(1).strip().strip("\"'")
    assert len(desc) <= 60, f"Description is {len(desc)} chars, max 60"


def test_contributor_credited():
    path = os.path.join(SKILL_DIR, "SKILL.md")
    with open(path) as f:
        content = f.read()
    match = re.search(r"^author:\s*(.+)$", content, re.MULTILINE)
    assert match, "author not found"
    assert "NJL" in match.group(1), "Human contributor not credited"


def test_registry_is_valid_json():
    path = os.path.join(SKILL_DIR, "references", "jargon-registry.json")
    assert os.path.exists(path), f"Registry not found at {path}"
    with open(path) as f:
        data = json.load(f)
    assert isinstance(data, dict), f"Registry root should be dict, got {type(data)}"
    assert len(data) > 0, "Registry is empty"
    # Each entry must have required fields
    for term, entry in data.items():
        assert "term" in entry, f"Entry {term} missing term field"
        assert "plainspeak" in entry, f"Entry {term} missing plainspeak"
        assert "kindergarten" in entry["plainspeak"], f"Entry {term} missing kindergarten level"


def test_registry_path_consistent():
    """SKILL.md must reference the correct registry path."""
    path = os.path.join(SKILL_DIR, "SKILL.md")
    with open(path) as f:
        content = f.read()
    # Should reference references/jargon-registry.json not a bare jargon-registry.json
    assert "references/jargon-registry.json" in content, "SKILL.md references wrong registry path"


def test_no_windows_in_platforms():
    path = os.path.join(SKILL_DIR, "SKILL.md")
    with open(path) as f:
        content = f.read()
    match = re.search(r"platforms:\s*\[([^\]]*)\]", content)
    if match:
        platforms = [p.strip() for p in match.group(1).split(",")]
        assert "windows" not in platforms, "Windows declared but skill uses Bash/bash-only features"
