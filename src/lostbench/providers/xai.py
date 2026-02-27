"""xAI provider adapter."""

import asyncio
import logging
import os

import openai

from lostbench.providers.base import Provider
from lostbench.retry import retry_with_backoff

logger = logging.getLogger(__name__)

_REASONING_PATTERNS = ("reasoning", "think")
_EMPTY_RESPONSE_RETRIES = 3
_EMPTY_RESPONSE_BASE_DELAY = 2.0


def _is_reasoning_model(model: str) -> bool:
    """Detect reasoning models that reject temperature/seed params."""
    return any(p in model.lower() for p in _REASONING_PATTERNS)


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
        self._reasoning_client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1",
            timeout=180.0,
        )

    @property
    def supports_seed(self) -> bool:
        return True

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.0,
        seed: int = 42,
    ) -> str:
        reasoning = _is_reasoning_model(model or "")

        if reasoning:
            logger.info(
                "Reasoning model detected (%s): skipping temperature/seed, "
                "using 180s timeout",
                model,
            )

        async def _call():
            if reasoning:
                return await self._reasoning_client.chat.completions.create(
                    model=model,
                    messages=messages,
                )
            return await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                seed=seed,
            )

        model_str = model or "unknown"
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
                    "Empty response from xAI API (model=%s, "
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
                    f"Empty response from xAI API after "
                    f"{_EMPTY_RESPONSE_RETRIES + 1} attempts "
                    f"(model={model_str}, finish_reason={finish})"
                )
            return text
        raise ValueError(f"Empty response from xAI API (model={model_str})")
