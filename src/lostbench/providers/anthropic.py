"""Anthropic provider adapter."""

import anthropic

from lostbench.providers.base import Provider


class AnthropicProvider(Provider):
    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic()

    async def chat(self, messages: list[dict], model: str | None = None,
                   temperature: float = 0.0, seed: int = 42) -> str:
        system_content = None
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                system_content = m["content"]
            else:
                chat_messages.append(m)

        kwargs = dict(
            model=model,
            max_tokens=4096,
            messages=chat_messages,
            temperature=temperature,
        )
        if system_content:
            kwargs["system"] = system_content

        response = await self._client.messages.create(**kwargs)
        return response.content[0].text
