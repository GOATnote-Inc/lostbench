"""Caching provider wrapper.

Wraps any Provider with a deterministic disk-based response cache.
Identical requests (same model, messages, temperature, seed) return
cached responses without API calls.
"""

from lostbench.cache import ResponseCache
from lostbench.providers.base import Provider


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
            model or "", messages, temperature, seed,
        )
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        response = await self._provider.chat(
            messages, model=model, temperature=temperature, seed=seed,
        )
        self._cache.put(key, response, model or "")
        return response
