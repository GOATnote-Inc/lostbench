"""xAI provider adapter."""

import openai

from lostbench.providers.base import Provider
from lostbench.retry import retry_with_backoff


class XAIProvider(Provider):
    """xAI provider using OpenAI-compatible API."""

    def __init__(self) -> None:
        self._client = openai.AsyncOpenAI(
            base_url="https://api.x.ai/v1",
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
            raise ValueError(f"Empty response from xAI API (model={model})")
        return response.choices[0].message.content
