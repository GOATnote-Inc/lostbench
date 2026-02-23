"""Tests for deterministic response cache."""

import json

from lostbench.cache import ResponseCache


class TestResponseCache:
    """Tests for disk-based response cache."""

    def test_cache_miss_then_hit(self, tmp_path):
        cache = ResponseCache(str(tmp_path))
        key = ResponseCache.cache_key(
            "model", [{"role": "user", "content": "hi"}], 0.0, 42
        )

        assert cache.get(key) is None
        assert cache.stats["misses"] == 1

        cache.put(key, "hello back", "model")
        assert cache.get(key) == "hello back"
        assert cache.stats["hits"] == 1

    def test_cache_key_deterministic(self):
        msgs = [{"role": "user", "content": "test"}]
        k1 = ResponseCache.cache_key("m", msgs, 0.0, 42)
        k2 = ResponseCache.cache_key("m", msgs, 0.0, 42)
        assert k1 == k2

    def test_cache_key_varies_with_model(self):
        msgs = [{"role": "user", "content": "test"}]
        k1 = ResponseCache.cache_key("gpt-5.2", msgs, 0.0, 42)
        k2 = ResponseCache.cache_key("claude-sonnet", msgs, 0.0, 42)
        assert k1 != k2

    def test_cache_key_varies_with_messages(self):
        k1 = ResponseCache.cache_key("m", [{"role": "user", "content": "a"}], 0.0, 42)
        k2 = ResponseCache.cache_key("m", [{"role": "user", "content": "b"}], 0.0, 42)
        assert k1 != k2

    def test_cache_key_varies_with_seed(self):
        msgs = [{"role": "user", "content": "test"}]
        k1 = ResponseCache.cache_key("m", msgs, 0.0, 42)
        k2 = ResponseCache.cache_key("m", msgs, 0.0, 99)
        assert k1 != k2

    def test_integrity_check_detects_corruption(self, tmp_path):
        cache = ResponseCache(str(tmp_path))
        key = ResponseCache.cache_key("m", [{"role": "user", "content": "hi"}], 0.0, 42)
        cache.put(key, "original response", "m")

        # Corrupt the cached file
        entry_path = cache._entry_path(key)
        with open(entry_path) as f:
            entry = json.load(f)
        entry["response"] = "tampered response"
        with open(entry_path, "w") as f:
            json.dump(entry, f)

        # Should detect corruption and return None
        assert cache.get(key) is None
        assert cache.stats["misses"] >= 1

    def test_corruption_quarantines_entry(self, tmp_path):
        """Corrupted entries are moved to quarantine dir, not deleted."""
        cache = ResponseCache(str(tmp_path))
        key = ResponseCache.cache_key("m", [{"role": "user", "content": "q"}], 0.0, 42)
        cache.put(key, "original", "m")

        # Corrupt
        entry_path = cache._entry_path(key)
        with open(entry_path) as f:
            entry = json.load(f)
        entry["response"] = "tampered"
        with open(entry_path, "w") as f:
            json.dump(entry, f)

        cache.get(key)

        # Original path removed
        assert not entry_path.exists()
        # Quarantine dir has the entry
        quarantine_path = tmp_path / ".cache_corrupted" / f"{key}.json"
        assert quarantine_path.exists()
        with open(quarantine_path) as f:
            q_entry = json.load(f)
        assert q_entry["response"] == "tampered"

    def test_corruption_events_in_stats(self, tmp_path):
        cache = ResponseCache(str(tmp_path))
        key = ResponseCache.cache_key("m", [{"role": "user", "content": "c"}], 0.0, 42)
        cache.put(key, "original", "m")

        entry_path = cache._entry_path(key)
        with open(entry_path) as f:
            entry = json.load(f)
        entry["response"] = "tampered"
        with open(entry_path, "w") as f:
            json.dump(entry, f)

        cache.get(key)
        assert cache.stats["corruption_events"] == 1

    def test_no_corruption_events_key_absent(self, tmp_path):
        """Stats omit corruption_events when there are none."""
        cache = ResponseCache(str(tmp_path))
        assert "corruption_events" not in cache.stats

    def test_stats_tracking(self, tmp_path):
        cache = ResponseCache(str(tmp_path))
        key = ResponseCache.cache_key("m", [{"role": "user", "content": "hi"}], 0.0, 42)

        cache.get(key)  # miss
        cache.put(key, "resp", "m")
        cache.get(key)  # hit
        cache.get(key)  # hit

        assert cache.stats == {"hits": 2, "misses": 1, "total": 3, "hit_rate": 2 / 3}

    def test_cache_persists_across_instances(self, tmp_path):
        cache1 = ResponseCache(str(tmp_path))
        key = ResponseCache.cache_key("m", [{"role": "user", "content": "hi"}], 0.0, 42)
        cache1.put(key, "persisted", "m")

        cache2 = ResponseCache(str(tmp_path))
        assert cache2.get(key) == "persisted"

    def test_subdirectory_structure(self, tmp_path):
        cache = ResponseCache(str(tmp_path))
        key = ResponseCache.cache_key("m", [{"role": "user", "content": "hi"}], 0.0, 42)
        cache.put(key, "resp", "m")

        # Entry should be in a two-char prefix subdirectory
        entry_path = cache._entry_path(key)
        assert entry_path.parent.name == key[:2]
