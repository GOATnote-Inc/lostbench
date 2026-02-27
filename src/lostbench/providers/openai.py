"""OpenAI provider adapter."""

import asyncio
import logging

import openai

from lostbench.providers.base import Provider
from lostbench.retry import retry_with_backoff

logger = logging.getLogger(__name__)

_EMPTY_RESPONSE_RETRIES = 3
_EMPTY_RESPONSE_BASE_DELAY = 2.0


class OpenAIProvider(Provider):
    def __init__(self) -> None:
        self._client = openai.AsyncOpenAI(timeout=60.0)

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.0,
        seed: int = 42,
    ) -> str:
        model_str = model or "unknown"

        async def _call():
            return await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                seed=seed,
            )

        for attempt in range(_EMPTY_RESPONSE_RETRIES + 1):
            response = await retry_with_backoff(_call)
            text = (
                (response.choices[0].message.content or "").strip()
                if response.choices
                else ""
            )
            if not text:
                finish = (
                    response.choices[0].finish_reason
                    if response.choices
                    else "no_choices"
                )
                logger.warning(
                    "Empty response from OpenAI API (model=%s, "
                    "finish_reason=%s, attempt %d/%d)",
                    model_str,
                    finish,
                    attempt + 1,
                    _EMPTY_RESPONSE_RETRIES + 1,
                )
                if attempt < _EMPTY_RESPONSE_RETRIES:
                    await asyncio.sleep(
                        _EMPTY_RESPONSE_BASE_DELAY * (2**attempt)
                    )
                    continue
                raise ValueError(
                    f"Empty response from OpenAI API after "
                    f"{_EMPTY_RESPONSE_RETRIES + 1} attempts "
                    f"(model={model_str}, finish_reason={finish})"
                )
            return text
        # Should not reach here, but satisfy type checker
        raise ValueError(f"Empty response from OpenAI API (model={model_str})")
