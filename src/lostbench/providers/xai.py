"""xAI provider adapter."""

import openai

from lostbench.providers.base import Provider


class XAIProvider(Provider):
    """xAI provider using OpenAI-compatible API."""

    def __init__(self) -> None:
        self._client = openai.AsyncOpenAI(
            base_url="https://api.x.ai/v1",
        )

    async def chat(self, messages: list[dict], model: str | None = None,
                   temperature: float = 0.0, seed: int = 42) -> str:
        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            seed=seed,
        )
        return response.choices[0].message.content
