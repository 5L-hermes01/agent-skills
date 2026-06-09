import time

from nyt_reader.cache import Cache


def test_set_get_json_roundtrip(tmp_cache_dir):
    c = Cache(tmp_cache_dir)
    c.set_json("GET", "https://example.test/a", {"x": 1})
    assert c.get_json("GET", "https://example.test/a", ttl=1000) == {"x": 1}


def test_ttl_expiry(tmp_cache_dir):
    import json
    c = Cache(tmp_cache_dir)
    c.set_json("GET", "https://example.test/b", {"y": 2})
    meta_files = list(tmp_cache_dir.glob("*.meta.json"))
    assert len(meta_files) == 1
    m = json.loads(meta_files[0].read_text())
    m["fetched_at"] = time.time() - 10_000
    meta_files[0].write_text(json.dumps(m))
    assert c.get_json("GET", "https://example.test/b", ttl=1000) is None


def test_miss_when_no_entry(tmp_cache_dir):
    c = Cache(tmp_cache_dir)
    assert c.get_json("GET", "https://example.test/missing", ttl=1000) is None


def test_bytes_roundtrip(tmp_cache_dir):
    c = Cache(tmp_cache_dir)
    p = c.set_bytes("GET", "https://cdn.test/x.mp3", b"\x00\x01")
    assert p.read_bytes() == b"\x00\x01"
    assert c.get_bytes_path("GET", "https://cdn.test/x.mp3", ttl=1000) == p
