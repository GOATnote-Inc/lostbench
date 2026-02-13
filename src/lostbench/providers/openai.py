"""OpenAI provider adapter."""

import openai

from lostbench.providers.base import Provider


class OpenAIProvider(Provider):
    def __init__(self) -> None:
        self._client = openai.AsyncOpenAI()

    async def chat(self, messages: list[dict], model: str | None = None,
                   temperature: float = 0.0, seed: int = 42) -> str:
        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            seed=seed,
        )
        if not response.choices or response.choices[0].message.content is None:
            raise ValueError(f"Empty response from OpenAI API (model={model})")
        return response.choices[0].message.content
