"""Smoke tests against synthetic fixtures. No live network. No real WaytoAGI content."""
from __future__ import annotations

import json

from waytoagi_reader.blocks import (
    block_children,
    find_heading,
    heading_level,
    normalize_heading,
    render_runs,
    render_text,
    split_mention_and_summary,
)
from waytoagi_reader.bootstrap import extract_blocks
from waytoagi_reader.update_log import collect_section, render


SYNTH_BLOCKS = {
    "root": {
        "id": "root",
        "data": {
            "type": "page",
            "parent_id": None,
            "children": ["h_target", "d_one", "i_one", "d_two", "i_two", "h_next"],
        },
    },
    "h_target": {
        "id": "h_target",
        "data": {
            "type": "heading1",
            "parent_id": "root",
            "children": [],
            "text": {
                "apool": {"numToAttrib": {}},
                "initialAttributedTexts": {"attribs": {"0": "+5"}, "text": {"0": "Foo日志"}},
            },
        },
    },
    "d_one": {
        "id": "d_one",
        "data": {
            "type": "heading3",
            "parent_id": "root",
            "children": [],
            "text": {
                "apool": {"numToAttrib": {}},
                "initialAttributedTexts": {"attribs": {"0": "+8"}, "text": {"0": "1 月 1 日"}},
            },
        },
    },
    "i_one": {
        "id": "i_one",
        "data": {
            "type": "bullet",
            "parent_id": "root",
            "children": [],
            "text": {
                "apool": {
                    "numToAttrib": {
                        "0": [
                            "inline-component",
                            json.dumps({
                                "id": "x",
                                "type": "mention_doc",
                                "data": {"title": "Synth Title 1", "raw_url": "https://example/1", "token": "tok1"},
                            }),
                        ]
                    }
                },
                "initialAttributedTexts": {
                    "attribs": {"0": "*0+1+8"},
                    "text": {"0": " summary1"},
                },
            },
        },
    },
    "d_two": {
        "id": "d_two",
        "data": {
            "type": "heading3",
            "parent_id": "root",
            "children": [],
            "text": {
                "apool": {"numToAttrib": {}},
                "initialAttributedTexts": {"attribs": {"0": "+8"}, "text": {"0": "1 月 2 日"}},
            },
        },
    },
    "i_two": {
        "id": "i_two",
        "data": {
            "type": "bullet",
            "parent_id": "root",
            "children": [],
            "text": {
                "apool": {"numToAttrib": {}},
                "initialAttributedTexts": {"attribs": {"0": "+13"}, "text": {"0": "plain summary"}},
            },
        },
    },
    "h_next": {
        "id": "h_next",
        "data": {
            "type": "heading1",
            "parent_id": "root",
            "children": [],
            "text": {
                "apool": {"numToAttrib": {}},
                "initialAttributedTexts": {"attribs": {"0": "+3"}, "text": {"0": "Bar"}},
            },
        },
    },
}


def test_heading_level():
    assert heading_level("heading1") == 1
    assert heading_level("heading3") == 3
    assert heading_level("bullet") is None


def test_normalize_heading_strips_emoji_and_whitespace():
    assert normalize_heading("🎏 近 7 日更新日志") == normalize_heading("近7日更新日志")


def test_find_heading_normalized():
    assert find_heading(SYNTH_BLOCKS, "Foo日志") == "h_target"
    assert find_heading(SYNTH_BLOCKS, "F o o 日 志") == "h_target"
    assert find_heading(SYNTH_BLOCKS, "Nope") is None


def test_find_heading_is_exact_by_default():
    """A partial substring must not match an unrelated heading — reviewer flagged
    the prior substring-only behavior as a false-positive risk."""
    assert find_heading(SYNTH_BLOCKS, "Foo") is None
    assert find_heading(SYNTH_BLOCKS, "Foo", fuzzy=True) == "h_target"


def test_collect_section_stops_at_same_level_heading():
    ids = collect_section(SYNTH_BLOCKS, "h_target")
    assert ids == ["d_one", "i_one", "d_two", "i_two"]


def test_render_groups_by_day_and_extracts_mentions():
    # The synth fixture in this file has bullets as siblings of the day headings.
    # The real Feishu structure has bullets as CHILDREN of the day heading, so
    # we rewire two fixtures here to reflect that.
    blocks = {bid: {**b, "data": {**b["data"]}} for bid, b in SYNTH_BLOCKS.items()}
    blocks["root"]["data"]["children"] = ["h_target", "d_one", "d_two", "h_next"]
    blocks["d_one"]["data"]["children"] = ["i_one"]
    blocks["i_one"]["data"]["parent_id"] = "d_one"
    blocks["d_two"]["data"]["children"] = ["i_two"]
    blocks["i_two"]["data"]["parent_id"] = "d_two"

    out = render(blocks, heading="Foo日志", source_url="https://example/")
    assert out["found"] is True
    assert out["schema_version"] == 1
    assert [d["heading"] for d in out["days"]] == ["1 月 1 日", "1 月 2 日"]
    item1 = out["days"][0]["items"][0]
    assert item1["title"] == "Synth Title 1"
    assert item1["url"] == "https://example/1"
    assert item1["summary"] == "summary1"
    item2 = out["days"][1]["items"][0]
    assert item2["title"] is None
    assert item2["summary"] == "plain summary"


def test_render_missing_heading():
    out = render(SYNTH_BLOCKS, heading="Missing", source_url="https://example/")
    assert out["found"] is False
    assert out["days"] == []


def test_extract_blocks_balanced_parse():
    snippet = (
        '<html><script>window.x = {'
        '"abcdefghij":{"id":"abcdefghij","version":1,"data":{"type":"heading1","text":{"nested":"}{"}}}'
        '};</script></html>'
    )
    blocks = extract_blocks(snippet)
    assert "abcdefghij" in blocks
    assert blocks["abcdefghij"]["data"]["type"] == "heading1"


def test_split_mention_and_summary_only_first_mention_is_link():
    parts = render_runs(SYNTH_BLOCKS["i_one"])
    assert any(isinstance(p, dict) for p in parts)
    mention, summary = split_mention_and_summary(SYNTH_BLOCKS["i_one"])
    assert mention["url"] == "https://example/1"
    assert summary == "summary1"


def test_render_text_renders_mentions_as_book_quotes():
    # The mention run consumes 1 char of placeholder text; the remaining 8 chars
    # are the plain summary. No extra space is introduced.
    assert render_text(SYNTH_BLOCKS["i_one"]) == "《Synth Title 1》summary1"


def test_render_day_missing_children_diagnostic(capsys):
    """A day heading whose children ids are absent from the payload must emit an
    accurate 'absent from SSR payload' warning, not the old misleading
    'possible older Feishu encoding' message. Synthetic fixture reproduces the
    real archive case (day references child ids that don't exist in the tree)."""
    from waytoagi_reader.update_log import _render_day

    blocks = {
        "d": {"id": "d", "data": {
            "type": "heading3", "parent_id": "root",
            "children": ["missing_1", "missing_2", "missing_3"],
            "text": {"apool": {"numToAttrib": {}},
                     "initialAttributedTexts": {"attribs": {"0": "+8"}, "text": {"0": "1 月 1 日"}}},
        }},
    }
    out = _render_day(blocks, "d")
    assert out["items"] == []
    err = capsys.readouterr().err
    assert "NONE are present in the SSR payload" in err
    assert "possible older Feishu encoding" not in err


def test_render_day_partial_missing_children_diagnostic(capsys):
    """Mixed case: some children present, some absent, and the present ones
    render nothing — warn with the partial-absence message."""
    from waytoagi_reader.update_log import _render_day

    blocks = {
        "d": {"id": "d", "data": {
            "type": "heading3", "parent_id": "root",
            "children": ["missing_1", "present_empty"],
            "text": {"apool": {"numToAttrib": {}},
                     "initialAttributedTexts": {"attribs": {"0": "+8"}, "text": {"0": "1 月 2 日"}}},
        }},
        "present_empty": {"id": "present_empty", "data": {
            "type": "bullet", "parent_id": "d", "children": [],
            "text": {"apool": {"numToAttrib": {}},
                     "initialAttributedTexts": {"attribs": {"0": "+0"}, "text": {"0": ""}}},
        }},
    }
    out = _render_day(blocks, "d")
    assert out["items"] == []
    err = capsys.readouterr().err
    assert "1 of 2 child block(s) absent from the SSR payload" in err
    assert "possible older Feishu encoding" not in err
