"""Caching provider wrapper.

Wraps any Provider with a deterministic disk-based response cache.
Identical requests (same model, messages, temperature, seed) return
cached responses without API calls.
"""

import json
import logging

from lostbench.cache import ResponseCache
from lostbench.providers.base import ChatResponse, Provider

logger = logging.getLogger(__name__)


class CachedProvider(Provider):
    """Provider wrapper that caches responses to disk.

    Transparent to callers — same interface as any Provider.
    Cache is keyed on (model, messages, temperature, seed) so
    deterministic settings produce cache hits on reruns.
    """

    def __init__(self, provider: Provider, cache: ResponseCache) -> None:
        self._provider = provider
        self._cache = cache

    @property
    def supports_seed(self) -> bool:
        return self._provider.supports_seed

    @property
    def cache(self) -> ResponseCache:
        return self._cache

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.0,
        seed: int = 42,
    ) -> str:
        key = ResponseCache.cache_key(
            model or "",
            messages,
            temperature,
            seed,
        )
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        response = await self._provider.chat(
            messages,
            model=model,
            temperature=temperature,
            seed=seed,
        )
        self._cache.put(key, response, model or "")
        return response

    async def chat_rich(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.0,
        seed: int = 42,
    ) -> ChatResponse:
        key = ResponseCache.cache_key(
            model or "",
            messages,
            temperature,
            seed,
        )
        cached = self._cache.get(key)
        if cached is not None:
            # Backward compat: old cache entries are plain text strings.
            # New entries are JSON with metadata.
            try:
                data = json.loads(cached)
                if isinstance(data, dict) and "text" in data:
                    return ChatResponse(
                        text=data["text"],
                        model_version=data.get("model_version", ""),
                        request_id=data.get("request_id", ""),
                        usage=data.get("usage", {}),
                        raw_body=data.get("raw_body", ""),
                    )
            except (json.JSONDecodeError, TypeError):
                pass
            # Plain text cache entry
            return ChatResponse(text=cached, model_version=model or "")

        resp = await self._provider.chat_rich(
            messages,
            model=model,
            temperature=temperature,
            seed=seed,
        )
        # Store as JSON with metadata for future rich lookups
        cache_value = json.dumps(
            {
                "text": resp.text,
                "model_version": resp.model_version,
                "request_id": resp.request_id,
                "usage": resp.usage,
                "raw_body": resp.raw_body,
            }
        )
        self._cache.put(key, cache_value, model or "")
        return resp
