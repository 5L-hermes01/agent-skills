import pytest

from translate.backends.openai_compat import OpenAICompatBackend


@pytest.mark.parametrize("body", [
    {}, {"choices": []}, {"choices": [{"finish_reason": "stop", "message": {"content": " "}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": None}}]},
    {"choices": [{"message": {"content": "unknown completion status"}}]},
    {"choices": [{"message": {"content": "partial"}, "finish_reason": "length"}]},
    {"choices": [{"message": {"content": "partial"}, "finish_reason": "content_filter"}]},
])
def test_rejects_incomplete_response(monkeypatch, body):
    backend = OpenAICompatBackend()
    monkeypatch.setattr(backend, "_post_with_retry", lambda *args: body)
    with pytest.raises(ValueError):
        backend.translate("中文", source="zh", target="en")


def test_budget_and_cache_identity(monkeypatch):
    monkeypatch.setenv("TRANSLATE_OPENAI_MAX_TOKENS", "8192")
    backend = OpenAICompatBackend(host="http://one", model="same")
    def post(url, payload):
        assert payload["max_tokens"] == 8192
        return {"choices": [{"finish_reason": "stop", "message": {"content": "Hello"}}]}
    monkeypatch.setattr(backend, "_post_with_retry", post)
    assert backend.translate("中文" * 1000, source="zh", target="en") == "Hello"
    assert backend.cache_signature() != OpenAICompatBackend(host="http://two", model="same").cache_signature()


def test_cli_does_not_cache_truncated_output(monkeypatch, tmp_path, capsys):
    import io
    import json
    import sys
    from translate import cli
    monkeypatch.setenv("TRANSLATE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"title":"中文"}'))
    monkeypatch.setattr(OpenAICompatBackend, "_post_with_retry", lambda *a: {
        "choices": [{"finish_reason": "length", "message": {"content": "partial"}}]})
    assert cli.main(["--target", "en", "--backend", "openai_compat"]) == cli.EXIT_BACKEND
    output = json.loads(capsys.readouterr().out)
    assert output["title_en"] is None
    assert "Incomplete" in output["title_en_error"]
    assert not list(tmp_path.rglob("*.json"))
