"""OpenAI provider adapter."""

import openai

from lostbench.providers.base import Provider
from lostbench.retry import retry_with_backoff


class OpenAIProvider(Provider):
    def __init__(self) -> None:
        self._client = openai.AsyncOpenAI(timeout=60.0)

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
            raise ValueError(f"Empty response from OpenAI API (model={model})")
        return text
