"""xAI provider adapter."""

import os

import openai

from lostbench.providers.base import Provider
from lostbench.retry import retry_with_backoff


class XAIProvider(Provider):
    """xAI provider using OpenAI-compatible API."""

    def __init__(self) -> None:
        api_key = os.environ.get("XAI_API_KEY")
        if not api_key:
            raise ValueError(
                "XAI_API_KEY environment variable is required for xAI provider"
            )
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1",
            timeout=60.0,
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
        text = (response.choices[0].message.content or "").strip() if response.choices else ""
        if not text:
            raise ValueError(f"Empty response from xAI API (model={model or 'unknown'})")
        return text
