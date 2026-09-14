"""Unit tests for the full-content pipeline. No network — exercises render + batching."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import waytoagi_content as C


def _block(text_raw, attribs="", apool=None, type_="text"):
    return {"data": {
        "type": type_,
        "children": [],
        "text": {
            "apool": {"numToAttrib": apool or {}},
            "initialAttributedTexts": {"attribs": {"0": attribs}, "text": {"0": text_raw}},
        },
    }}


def test_external_link_preserved():
    # raw "论文" (2 chars), run *1+1 covers first char with a link attrib, rest plain.
    # Build a minimal, unambiguous block: attrib *1+1 -> link on char[0:1].
    b = _block("论文", "*1+1*0+1", apool={
        "0": ["author", "x"],
        "1": ["link", "https://arxiv.org/abs/2608.18300"],
    })
    runs = C.render_content_runs(b)
    kinds = [(p.get("type"), p.get("url")) if isinstance(p, dict) else ("text", None) for p in runs]
    assert ("link", "https://arxiv.org/abs/2608.18300") in kinds
    # text is rendered verbatim
    txt = C.render_article_text(b)
    assert "https://arxiv.org/abs/2608.18300" in txt

    # internal feishu mention is NOT a markdown link
    b2 = _block("原帖", "*1+2", apool={
        "1": ["link", "https://waytoagi.feishu.cn/wiki/ABC"],
    })
    assert "https://waytoagi.feishu.cn/wiki/ABC" not in C.render_article_text(b2)


def test_needs_translation():
    assert C._needs_translation("本文为转载")
    assert not C._needs_translation("Top AI Papers of the Week")
    assert not C._needs_translation("")


def test_translate_text_splits_by_char_budget(monkeypatch):
    calls = []

    def fake_post(host, model, lines, timeout):
        calls.append(lines)
        # echo the [0] body
        return "\n".join(lines)
    monkeypatch.setattr(C, "_post", fake_post)
    monkeypatch.setenv("WAYTOAGI_BATCH_CHARS", "50")

    text = "\n\n".join(f"段落{i}一二三四五六七八九十" for i in range(6))
    out = C._translate_text("h", "m", text)
    assert len(calls) > 1  # split into multiple batches
    assert "段落0" in out


def test_skip_english_text(monkeypatch):
    monkeypatch.setattr(C, "_post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call")))
    assert C._translate_text("h", "m", "Already English content") == "Already English content"
