"""Anthropic provider adapter."""

import asyncio
import logging

import anthropic

from lostbench.providers.base import Provider
from lostbench.retry import retry_with_backoff

logger = logging.getLogger(__name__)

_EMPTY_RESPONSE_RETRIES = 3
_EMPTY_RESPONSE_BASE_DELAY = 2.0


class AnthropicProvider(Provider):
    @property
    def supports_seed(self) -> bool:
        return False

    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(timeout=300.0)
        logger.info(
            "Anthropic provider does not support seed parameter; "
            "results will not be deterministic"
        )

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.0,
        seed: int = 42,
    ) -> str:
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

        model_str = model or "unknown"

        async def _call():
            return await self._client.messages.create(**kwargs)

        for attempt in range(_EMPTY_RESPONSE_RETRIES + 1):
            response = await retry_with_backoff(_call)
            if not response.content:
                logger.warning(
                    "Empty response.content from Anthropic API (model=%s, "
                    "stop_reason=%s, attempt %d/%d)",
                    model_str,
                    getattr(response, "stop_reason", "unknown"),
                    attempt + 1,
                    _EMPTY_RESPONSE_RETRIES + 1,
                )
                if attempt < _EMPTY_RESPONSE_RETRIES:
                    await asyncio.sleep(_EMPTY_RESPONSE_BASE_DELAY * (2**attempt))
                    continue
                raise ValueError(
                    f"Empty response from Anthropic API after "
                    f"{_EMPTY_RESPONSE_RETRIES + 1} attempts "
                    f"(model={model_str}, stop_reason="
                    f"{getattr(response, 'stop_reason', 'unknown')})"
                )
            if not hasattr(response.content[0], "text"):
                raise ValueError(
                    f"Unexpected response format from Anthropic API (model={model_str})"
                )
            text = (response.content[0].text or "").strip()
            if not text:
                logger.warning(
                    "Empty text in response from Anthropic API (model=%s, "
                    "stop_reason=%s, attempt %d/%d)",
                    model_str,
                    response.stop_reason,
                    attempt + 1,
                    _EMPTY_RESPONSE_RETRIES + 1,
                )
                if attempt < _EMPTY_RESPONSE_RETRIES:
                    await asyncio.sleep(_EMPTY_RESPONSE_BASE_DELAY * (2**attempt))
                    continue
                raise ValueError(
                    f"Empty response from Anthropic API after "
                    f"{_EMPTY_RESPONSE_RETRIES + 1} attempts "
                    f"(model={model_str}, stop_reason={response.stop_reason})"
                )
            return text
        # Should not reach here, but satisfy type checker
        raise ValueError(f"Empty response from Anthropic API (model={model_str})")
