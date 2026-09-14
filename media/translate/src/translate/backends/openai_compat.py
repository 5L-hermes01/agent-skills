"""OpenAI-compatible backend. Hits any server exposing /v1/chat/completions
(e.g. llama.cpp server, vLLM, LiteLLM). Stdlib-only.

Config via env: TRANSLATE_OPENAI_HOST (default http://localhost:8000),
TRANSLATE_OPENAI_MODEL (default qwen3.8), TRANSLATE_TIMEOUT_MS,
TRANSLATE_OPENAI_MAX_TOKENS (default 16000; length-terminated output fails).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request


_SYSTEM_PROMPT = (
    "You are a precise translator. Translate the user's text into the target language. "
    "Preserve proper nouns, product names, code identifiers, URLs, and numbers exactly. "
    "Do not add commentary or wrap the output in quotes — return only the translated text."
)

_DEFAULT_MAX_RETRIES = 2
_BACKOFF_BASE_SEC = 0.5


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return 500 <= exc.code < 600
    return isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError))


class OpenAICompatBackend:
    name = "openai_compat"

    def __init__(self, *, model: str | None = None, host: str | None = None, timeout: float | None = None):
        self.model = model or os.environ.get("TRANSLATE_OPENAI_MODEL", "qwen3.8")
        self.host = (host or os.environ.get("TRANSLATE_OPENAI_HOST", "http://localhost:8000")).rstrip("/")
        timeout_ms = int(os.environ.get("TRANSLATE_TIMEOUT_MS", "60000"))
        self.timeout = (timeout if timeout is not None else timeout_ms / 1000.0)
        self.max_retries = int(os.environ.get("TRANSLATE_MAX_RETRIES", str(_DEFAULT_MAX_RETRIES)))
        self.max_tokens = int(os.environ.get("TRANSLATE_OPENAI_MAX_TOKENS", "16000"))
        if self.max_tokens <= 0:
            raise ValueError("TRANSLATE_OPENAI_MAX_TOKENS must be positive")

    def cache_signature(self) -> str:
        prompt_digest = hashlib.sha256(_SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:16]
        host_digest = hashlib.sha256(self.host.encode("utf-8")).hexdigest()[:16]
        return f"openai_compat:v2:{host_digest}:{self.model}:{prompt_digest}:{self.max_tokens}"

    def translate(self, text: str, *, source: str, target: str) -> str:
        prompt = (
            f"Source language: {source}\n"
            f"Target language: {target}\n"
            f"Text:\n{text}"
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        body = self._post_with_retry(f"{self.host}/v1/chat/completions", payload)
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError("Translation response has no usable choice")
        choice = choices[0]
        content = (choice.get("message") or {}).get("content")
        if choice.get("finish_reason") != "stop":
            raise ValueError(f"Incomplete translation: {choice.get('finish_reason')}")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Translation response has no text")
        return content.strip()

    def _post_with_retry(self, url: str, payload: dict) -> dict:
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL scheme: {url}")

        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                    return json.loads(resp.read())
            except Exception as exc:  # noqa: BLE001
                if attempt >= self.max_retries or not _is_retryable(exc):
                    raise
                time.sleep(_BACKOFF_BASE_SEC * (2 ** attempt))
        raise RuntimeError("unreachable")  # pragma: no cover
