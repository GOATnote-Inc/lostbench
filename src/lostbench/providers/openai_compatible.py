"""OpenAI-compatible provider adapter for local/third-party endpoints."""

import os

import openai

from lostbench.providers.base import Provider
from lostbench.retry import retry_with_backoff


class OpenAICompatibleProvider(Provider):
    """Provider for any OpenAI-compatible API (ollama, vLLM, Together, etc.)."""

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        resolved_key = api_key or os.environ.get("OPENAI_COMPATIBLE_API_KEY", "no-key")
        self._client = openai.AsyncOpenAI(
            api_key=resolved_key,
            base_url=base_url,
        )

    async def chat(self, messages: list[dict], model: str | None = None,
                   temperature: float = 0.0, seed: int = 42) -> str:
        async def _call():
            return await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                seed=seed,
            )
        response = await retry_with_backoff(_call)
        if not response.choices or response.choices[0].message.content is None:
            raise ValueError(f"Empty response from API at {self._client.base_url} (model={model})")
        return response.choices[0].message.content
