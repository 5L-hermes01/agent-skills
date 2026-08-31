"""Backend protocol + registry. Selected at runtime by TRANSLATE_BACKEND env or --backend."""
from __future__ import annotations

import os
from typing import Protocol


class Backend(Protocol):
    name: str

    def translate(self, text: str, *, source: str, target: str) -> str: ...

    def cache_signature(self) -> str:
        """Return a stable identifier covering everything that affects the output:
        backend name, model id, and a digest of the system prompt. Used as a cache-key
        component so any change to those invalidates affected entries automatically."""
        ...


def get_backend(name: str | None = None, *, model: str | None = None):
    name = name or os.environ.get("TRANSLATE_BACKEND", "ollama")
    if name == "noop":
        from .noop import NoopBackend
        return NoopBackend()
    if name == "ollama":
        from .ollama import OllamaBackend
        return OllamaBackend(model=model)
    if name == "openai_compat":
        from .openai_compat import OpenAICompatBackend
        return OpenAICompatBackend(model=model)
    raise ValueError(f"unknown backend: {name}")
