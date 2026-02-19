"""Anthropic provider adapter."""

import anthropic

from lostbench.providers.base import Provider
from lostbench.retry import retry_with_backoff


class AnthropicProvider(Provider):
    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(timeout=60.0)

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

        async def _call():
            return await self._client.messages.create(**kwargs)

        response = await retry_with_backoff(_call)
        model_str = model or "unknown"
        if not response.content:
            raise ValueError(f"Empty response from Anthropic API (model={model_str})")
        if not hasattr(response.content[0], "text"):
            raise ValueError(f"Unexpected response format from Anthropic API (model={model_str})")
        text = (response.content[0].text or "").strip()
        if not text:
            raise ValueError(f"Empty response from Anthropic API (model={model_str})")
        return text
