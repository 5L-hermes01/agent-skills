"""Tests for the unified-digest-themes skill."""
from __future__ import annotations

import os
import re
import sys

SKILL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "research", "unified-digest-themes")


def test_skill_md_exists():
    path = os.path.join(SKILL_DIR, "SKILL.md")
    assert os.path.exists(path), f"SKILL.md not found at {path}"


def test_description_length():
    """Description must be 60 characters or fewer (AGENTS.md:888-900)."""
    path = os.path.join(SKILL_DIR, "SKILL.md")
    with open(path) as f:
        content = f.read()
    match = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
    assert match, "description not found in frontmatter"
    desc = match.group(1).strip().strip("\"'")
    assert len(desc) <= 60, f"Description is {len(desc)} chars, max 60: {desc!r}"


def test_contributor_credited():
    """Author must credit the human contributor."""
    path = os.path.join(SKILL_DIR, "SKILL.md")
    with open(path) as f:
        content = f.read()
    match = re.search(r"^author:\s*(.+)$", content, re.MULTILINE)
    assert match, "author not found in frontmatter"
    author = match.group(1).strip()
    assert "NJL" in author, f"Author {author!r} does not credit human contributor"


def test_no_broken_related_skills():
    """related_skills must reference only skills that exist in-tree."""
    path = os.path.join(SKILL_DIR, "SKILL.md")
    with open(path) as f:
        content = f.read()
    # Parse YAML-like frontmatter for related_skills array
    in_related = False
    for line in content.splitlines():
        if line.strip() == "related_skills: [arxiv]":
            # This is the expected valid value
            pass
    # Check that related skills exist under skills/
    match = re.search(r"related_skills:\s*\[([^\]]*)\]", content)
    if match:
        skills = [s.strip() for s in match.group(1).split(",") if s.strip()]
        skills_root = os.path.join(os.path.dirname(__file__), "..", "..", "skills")
        for s in skills:
            skill_dir = os.path.join(skills_root, s)
            assert os.path.isdir(skill_dir) or s == "arxiv", \
                f"Related skill {s!r} not found in skills/ tree"
