import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import waytoagi_content as C
import waytoagi_translate as T
import waytoagi_pipeline as P
import translation_common as HTTP


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(C.time, "sleep", lambda _: None)


@pytest.mark.parametrize("module", [C, T])
@pytest.mark.parametrize("choice", [
    {}, {"finish_reason": "stop", "message": {"content": ""}},
    {"finish_reason": "stop", "message": {"content": None}},
    {"message": {"content": "unknown completion status"}},
    {"message": {"content": "partial"}, "finish_reason": "length"},
])
def test_post_rejects_incomplete(monkeypatch, module, choice):
    body = {"choices": [choice]}
    monkeypatch.setattr(HTTP.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(body).encode()))
    with pytest.raises(ValueError):
        module._post("http://test", "model", ["中文"], 1)


def test_batch_partial_falls_back_without_caching(monkeypatch, tmp_path):
    monkeypatch.setenv("WAYTOAGI_TRANSLATE_CACHE", str(tmp_path))
    calls = []
    def post(host, model, lines, timeout):
        calls.append(lines)
        return "[0] Hello" if len(lines) > 1 else "[0] Complete"
    monkeypatch.setattr(T, "_post", post)
    assert T._translate_batch("h", "m", [(0, "你"), (1, "好")], True) == {0: "Complete", 1: "Complete"}
    assert len(calls) == 5
    assert T._cache_get(tmp_path, "你", "h", "m") == "Complete"


def test_translation_failure_is_not_success(monkeypatch):
    monkeypatch.setattr(T, "_post", lambda *a, **k: "[0] ")
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"items":[{"title":"你"}]}'))
    assert T.main(["--no-cache"]) != 0


@pytest.mark.parametrize("days", [["10 月 1 日", "9 月 30 日"], ["1 月 1 日", "12 月 31 日"], ["8 月 10 日", "8 月 9 日"]])
def test_latest_uses_feed_order_even_without_chinese(monkeypatch, capsys, days):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"items": [{"day": d, "title": "English"} for d in days]})))
    assert T.main(["--latest-day", "--no-cache"]) == 0
    assert [i["day"] for i in json.loads(capsys.readouterr().out)["items"]] == days[:1]


def test_oversized_block_is_bounded(monkeypatch):
    monkeypatch.setenv("WAYTOAGI_BATCH_CHARS", "20")
    calls = []
    def post(host, model, lines, timeout):
        calls.append(lines[0][4:])
        return "translated"
    monkeypatch.setattr(C, "_post", post)
    C._translate_text("h", "m", "中" * 51)
    assert all(len(c) <= 20 for c in calls)
    assert "".join(calls) == "中" * 51


def test_failed_chunk_raises(monkeypatch):
    monkeypatch.setenv("WAYTOAGI_BATCH_CHARS", "2")
    calls = iter(["ok", "", "", ""])
    monkeypatch.setattr(C, "_post", lambda *a, **k: next(calls))
    with pytest.raises(RuntimeError):
        C._translate_text("h", "m", "中文中文")


def test_pipeline_rejects_partial_content(monkeypatch, tmp_path):
    monkeypatch.setitem(P.OUT, "daily", (str(tmp_path / "out.json"), []))
    responses = iter([{"items": [{"title": "English", "url": "http://article"}]}] * 3)
    monkeypatch.setattr(P, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(next(responses)), stderr=""))
    assert P.main(["daily"]) == 1
    assert not (tmp_path / "out.json").exists()


def test_pipeline_checkout_path():
    assert Path(P.WTR) == Path(P.__file__).resolve().parents[1]


def block(text, kind="text", children=None):
    return {"data": {"type": kind, "children": children or [], "text": {
        "initialAttributedTexts": {"text": {"0": text}}, "apool": {"numToAttrib": {}}
    }}}


def test_article_preserves_textual_blocks_and_rejects_missing():
    blocks = {"root": block("", "page", ["code", "table", "ordered"]),
              "code": block("print('hello')", "code"),
              "table": block("", "table", ["cell"]),
              "cell": block("Table cell", "table_cell"),
              "ordered": block("Last item", "ordered")}
    assert C.render_page_body(blocks) == "print('hello')\n\nTable cell\n\nLast item"
    del blocks["cell"]
    with pytest.raises(ValueError, match="absent"):
        C.render_page_body(blocks)


@pytest.mark.parametrize("text,children,expected", [
    ("item", ["present", "missing"], "present blocks rendered 1 items"),
    ("", ["present"], "0 renderable children although all referenced"),
    ("", [], "0 child blocks"),
])
def test_archive_diagnostics(capsys, text, children, expected):
    from waytoagi_reader.update_log import _render_day
    _render_day({"day": block("1 月 1 日", "heading3", children), "present": block(text)}, "day")
    assert expected in capsys.readouterr().err


def test_archive_raw_dump(monkeypatch, capsys):
    from waytoagi_reader import cli
    calls = []
    def fetch(url, mode):
        calls.append(url)
        return {"archive" if url == "archive" else "main": {}}
    monkeypatch.setattr(cli, "_fetch_and_extract", fetch)
    monkeypatch.setattr(cli, "_resolve_archive_url", lambda _: "archive")
    assert cli.main(["update-log", "--archive", "--emit-raw-blocks"]) == 0
    assert json.loads(capsys.readouterr().out) == {"archive": {}}
    assert len(calls) == 2


def test_content_cache_identity_expiry_and_legacy(monkeypatch, tmp_path):
    import os
    monkeypatch.setenv("WAYTOAGI_CONTENT_CACHE", str(tmp_path))
    key = C._translation_key("url", "中文", "host", "model")
    C._cache_put(key, "en", "Hello")
    assert C._cache_get(key, "en") == "Hello"
    for args in [("url", "更新", "host", "model"), ("url", "中文", "other", "model"),
                 ("url", "中文", "host", "other")]:
        assert C._cache_get(C._translation_key(*args), "en") is None
    monkeypatch.setattr(C, "_SYSTEM_PROMPT", "new prompt")
    assert C._translation_key("url", "中文", "host", "model") != key
    os.utime(C._content_cache_path(key, "en"), (0, 0))
    assert C._cache_get(key, "en") is None
    assert C._content_cache_path("url", "en").parent.parent.name == "v2"


def test_content_failure_limit_and_no_cache(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("WAYTOAGI_MAX_ARTICLES", "1")
    monkeypatch.setenv("WAYTOAGI_CONTENT_CACHE", str(tmp_path))
    calls = []
    def fetch(url, *, use_cache):
        calls.append((url, use_cache))
        return {"p": block("", "page", ["b"]), "b": block("中文")}
    monkeypatch.setattr(C, "fetch_blocks", fetch)
    monkeypatch.setattr(C, "_post", lambda *a, **k: "")
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"items": [
        {"url": "first", "content_en": "stale"}, {"url": "second"}]})))
    assert C.main(["--no-cache"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert all("content_en" not in i for i in result["items"])
    assert calls == [("first", False)]
    assert not list(tmp_path.rglob("*.txt"))


def test_raw_fetch_no_cache(monkeypatch):
    from waytoagi_reader import cache, bootstrap
    calls = []
    def fetch(url, **kwargs):
        calls.append(kwargs["mode"])
        return SimpleNamespace(body="synthetic")
    monkeypatch.setattr(cache, "cached_fetch", fetch)
    monkeypatch.setattr(bootstrap, "extract_blocks", lambda _: {})
    C.fetch_blocks("url", use_cache=False)
    assert calls == ["no"]


def test_pipeline_rejects_missing_title(monkeypatch, tmp_path):
    output = tmp_path / "output.json"
    monkeypatch.setitem(P.OUT, "daily", (str(output), []))
    calls = []
    def run(*a, **k):
        calls.append(a)
        return SimpleNamespace(returncode=0, stdout='{"items":[{"title":"中文"}]}', stderr="")
    monkeypatch.setattr(P, "run", run)
    assert P.main(["daily"]) == 1
    assert len(calls) == 2
    assert not output.exists()


def test_pipeline_success(monkeypatch, tmp_path):
    output = tmp_path / "output.json"
    monkeypatch.setitem(P.OUT, "daily", (str(output), []))
    item = {"title": "中文", "url": "url"}
    responses = iter([{"items": [item]}, {"items": [{**item, "title_en": "Title"}]},
                      {"items": [{**item, "title_en": "Title", "content_zh": "文章", "content_en": "Article"}]}])
    monkeypatch.setattr(P, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(next(responses)), stderr=""))
    assert P.main(["daily"]) == 0
    assert json.loads(output.read_text())["items"][0]["content_en"] == "Article"


def test_content_success_cache_reuse_and_model_change(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("WAYTOAGI_CONTENT_CACHE", str(tmp_path))
    monkeypatch.delenv("WAYTOAGI_MAX_ARTICLES", raising=False)
    fetches, translations = [], []
    def fetch(url, **kwargs):
        fetches.append(url)
        return {"p": block("", "page", ["b"]), "b": block("中文")}
    def post(host, model, lines, timeout):
        translations.append(model)
        return "Article " + model
    monkeypatch.setattr(C, "fetch_blocks", fetch)
    monkeypatch.setattr(C, "_post", post)
    for model in ("one", "one", "two"):
        monkeypatch.setattr(sys, "stdin", io.StringIO('{"items":[{"url":"url"}]}'))
        assert C.main(["--model", model]) == 0
        assert json.loads(capsys.readouterr().out)["items"][0]["content_en"] == "Article " + model
    assert fetches == ["url"]
    assert translations == ["one", "two"]


def test_failed_article_never_cached_as_english(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("WAYTOAGI_CONTENT_CACHE", str(tmp_path))
    monkeypatch.setenv("WAYTOAGI_BATCH_CHARS", "2")
    monkeypatch.setattr(C, "fetch_blocks", lambda *a, **k: {"p": block("", "page", ["b"]), "b": block("中文中文")})
    replies = iter(["Good", "", "", ""])
    monkeypatch.setattr(C, "_post", lambda *a, **k: next(replies))
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"items":[{"url":"url"}]}'))
    assert C.main([]) == 1
    assert "content_en" not in json.loads(capsys.readouterr().out)["items"][0]
    assert not list((tmp_path / "v2/en").glob("*.txt"))


def test_chunk_boundaries_preserve_links_and_skip_whitespace(monkeypatch):
    monkeypatch.setenv("WAYTOAGI_BATCH_CHARS", "30")
    calls = []
    def post(host, model, lines, timeout):
        calls.append(lines[0][4:])
        return "Introduction\n[0] reference"
    monkeypatch.setattr(C, "_post", post)
    link = "[标签](https://example.test)"
    result = C._translate_text("h", "m", "\n" + "中" * 15 + link + "文" * 15)
    assert all(c.strip() and len(c) <= 30 for c in calls)
    assert sum(link in c for c in calls) == 1
    assert "Introduction" in result
    monkeypatch.setenv("WAYTOAGI_BATCH_CHARS", "10")
    with pytest.raises(ValueError, match="link exceeds"):
        C._translate_text("h", "m", link)


@pytest.mark.parametrize("module", [C, T])
def test_post_accepts_completed_response(monkeypatch, module):
    response = {"choices": [{"finish_reason": "stop", "message": {"content": " Hello "}}]}
    monkeypatch.setattr(HTTP.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(response).encode()))
    assert module._post("http://test", "model", ["中文"], 1) == "Hello"


def source_blocks():
    blocks = {
        "root": block("Archive", "page", ["section", "good", "partial"]),
        "section": block("近 7 日更新日志", "heading2"),
        "good": block("1 月 2 日", "heading3", ["item"]),
        "partial": block("1 月 1 日", "heading3", ["item", "missing"]),
        "item": block("English summary"),
    }
    for bid in ("section", "good", "partial"):
        blocks[bid]["data"]["parent_id"] = "root"
    return blocks


@pytest.mark.parametrize("archive", [False, True])
@pytest.mark.parametrize("flatten", [False, True])
@pytest.mark.parametrize("date,expected", [(None, 5), ("1 月 1 日", 5), ("1 月 2 日", 0)])
def test_cli_rejects_only_retained_incomplete_days(monkeypatch, capsys, archive, flatten, date, expected):
    from waytoagi_reader import cli
    monkeypatch.setattr(cli, "_fetch_and_extract", lambda *a: source_blocks())
    monkeypatch.setattr(cli, "_resolve_archive_url", lambda _: "archive")
    args = ["update-log"] + (["--archive"] if archive else []) + (["--flatten"] if flatten else [])
    if date:
        args += ["--date", date]
    assert cli.main(args) == expected
    captured = capsys.readouterr()
    assert "Missing ids: missing" in captured.err
    if expected:
        assert captured.out == ""
        assert "[err]" in captured.err
    else:
        assert "English summary" in captured.out


def test_pipeline_stops_on_incomplete_source(monkeypatch, tmp_path):
    from contextlib import redirect_stdout, redirect_stderr
    from waytoagi_reader import cli
    monkeypatch.setattr(cli, "_fetch_and_extract", lambda *a: source_blocks())
    output = tmp_path / "output.json"
    output.write_text("previous complete output")
    monkeypatch.setitem(P.OUT, "daily", (str(output), []))
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd)
        assert len(calls) == 1, "Translation must not start on incomplete source"
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(["update-log", "--flatten"])
        return SimpleNamespace(returncode=code, stdout=stdout.getvalue(), stderr=stderr.getvalue())
    monkeypatch.setattr(P, "run", run)
    assert P.main(["daily"]) == 1
    assert len(calls) == 1
    assert output.read_text() == "previous complete output"


def test_pipeline_overlapping_publications_use_unique_temporaries(monkeypatch, tmp_path):
    output = tmp_path / "output.json"
    monkeypatch.setitem(P.OUT, "daily", (str(output), []))
    monkeypatch.setattr(P, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout='{"items":[]}', stderr=""))
    replace = P.os.replace
    sources = []
    def overlap(source, destination):
        source = Path(source)
        assert source.parent == output.parent
        assert source.exists()
        sources.append(source)
        if len(sources) == 1:
            assert P.main(["daily"]) == 0
        replace(source, destination)
    monkeypatch.setattr(P.os, "replace", overlap)
    assert P.main(["daily"]) == 0
    assert len(set(sources)) == 2
    assert json.loads(output.read_text()) == {"items": []}
    assert list(tmp_path.iterdir()) == [output]


def test_pipeline_cleans_temporary_on_publication_failure(monkeypatch, tmp_path):
    output = tmp_path / "output.json"
    output.write_text("previous complete output")
    monkeypatch.setitem(P.OUT, "daily", (str(output), []))
    monkeypatch.setattr(P, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout='{"items":[]}', stderr=""))
    def fail(*args):
        raise OSError("replace failed")
    monkeypatch.setattr(P.os, "replace", fail)
    with pytest.raises(OSError, match="replace failed"):
        P.main(["daily"])
    assert output.read_text() == "previous complete output"
    assert list(tmp_path.iterdir()) == [output]
