"""Deterministic response cache for LostBench.

Caches API responses keyed by (model, conversation, temperature, seed).
Deterministic runs with identical inputs produce cache hits, avoiding
redundant API calls and enabling reproducibility verification.

Cache entries are integrity-verified via SHA-256 response hashes.
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)


CACHE_DIR_NAME = ".response_cache"


class ResponseCache:
    """Disk-based deterministic response cache.

    Each entry is a JSON file keyed by SHA-256(model + messages + temp + seed).
    Entries include response hash for integrity verification.
    """

    def __init__(self, cache_dir: str) -> None:
        self._dir = Path(cache_dir) / CACHE_DIR_NAME
        self._dir.mkdir(parents=True, exist_ok=True)
        self._quarantine_dir = Path(cache_dir) / ".cache_corrupted"
        self._hits = 0
        self._misses = 0
        self._corruption_events = 0

    @staticmethod
    def cache_key(
        model: str,
        messages: list[dict],
        temperature: float,
        seed: int,
    ) -> str:
        """Compute deterministic cache key from request parameters."""
        payload = json.dumps(
            {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "seed": seed,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def _entry_path(self, key: str) -> Path:
        # Use two-char prefix subdirectory to avoid huge flat directories
        return self._dir / key[:2] / f"{key}.json"

    def get(self, key: str) -> str | None:
        """Look up cached response. Returns response text or None."""
        path = self._entry_path(key)
        if not path.exists():
            self._misses += 1
            return None

        with open(path) as f:
            entry = json.load(f)

        # Integrity check
        response = entry["response"]
        expected_hash = entry.get("response_hash")
        if expected_hash:
            actual = hashlib.sha256(response.encode()).hexdigest()
            if actual != expected_hash:
                logger.error(
                    "INTEGRITY FAILURE: %s... (expected %s, got %s)",
                    key[:12],
                    expected_hash[:12],
                    actual[:12],
                )
                self._misses += 1
                self._corruption_events += 1
                # Quarantine instead of deleting for forensic inspection
                self._quarantine_dir.mkdir(parents=True, exist_ok=True)
                quarantine_path = self._quarantine_dir / f"{key}.json"
                path.rename(quarantine_path)
                return None

        self._hits += 1
        return response

    def put(
        self,
        key: str,
        response: str,
        model: str,
    ) -> None:
        """Store a response in the cache."""
        entry = {
            "model": model,
            "response": response,
            "response_hash": hashlib.sha256(response.encode()).hexdigest(),
            "cached_at": time.time(),
        }
        path = self._entry_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(entry, f, indent=2)
        os.replace(tmp, path)

    @property
    def stats(self) -> dict:
        """Return cache hit/miss statistics."""
        total = self._hits + self._misses
        stats = {
            "hits": self._hits,
            "misses": self._misses,
            "total": total,
            "hit_rate": self._hits / total if total > 0 else 0.0,
        }
        if self._corruption_events:
            stats["corruption_events"] = self._corruption_events
        return stats
