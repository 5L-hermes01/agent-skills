"""Tiered TTL file cache. Key = sha256(method + url). Stores JSON or bytes."""
from __future__ import annotations
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional


def default_cache_dir() -> Path:
    env = os.environ.get("WSJ_CACHE_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent / "cache"


class Cache:
    def __init__(self, base: Optional[Path] = None):
        self.base = Path(base) if base else default_cache_dir()
        self.base.mkdir(parents=True, exist_ok=True)

    def _key(self, method: str, url: str) -> str:
        return hashlib.sha256(f"{method.upper()} {url}".encode()).hexdigest()

    def _paths(self, key: str, binary: bool) -> tuple[Path, Path]:
        ext = "bin" if binary else "json"
        return self.base / f"{key}.{ext}", self.base / f"{key}.meta.json"

    def get_json(self, method: str, url: str, ttl: int) -> Optional[Any]:
        key = self._key(method, url)
        data_p, meta_p = self._paths(key, binary=False)
        if not (data_p.exists() and meta_p.exists()):
            return None
        meta = json.loads(meta_p.read_text())
        if time.time() - meta["fetched_at"] >= ttl:
            return None
        return json.loads(data_p.read_text())

    def set_json(self, method: str, url: str, value: Any) -> None:
        key = self._key(method, url)
        data_p, meta_p = self._paths(key, binary=False)
        data_p.write_text(json.dumps(value))
        meta_p.write_text(json.dumps({"fetched_at": time.time(), "url": url}))

    def get_bytes_path(self, method: str, url: str, ttl: int) -> Optional[Path]:
        key = self._key(method, url)
        data_p, meta_p = self._paths(key, binary=True)
        if not (data_p.exists() and meta_p.exists()):
            return None
        meta = json.loads(meta_p.read_text())
        if time.time() - meta["fetched_at"] >= ttl:
            return None
        return data_p

    def set_bytes(self, method: str, url: str, value: bytes) -> Path:
        key = self._key(method, url)
        data_p, meta_p = self._paths(key, binary=True)
        data_p.write_bytes(value)
        meta_p.write_text(json.dumps({"fetched_at": time.time(), "url": url}))
        return data_p


# TTLs in seconds
TTL_ARTICLE = 30 * 24 * 3600
TTL_AUDIO = 30 * 24 * 3600
TTL_HEADLINES = 60 * 60
TTL_AUDIO_RESOLVE = 30 * 24 * 3600
