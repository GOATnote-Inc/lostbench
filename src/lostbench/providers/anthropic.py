"""Anthropic provider adapter."""

import asyncio
import json
import logging
import os

import anthropic

from lostbench.providers.base import ChatResponse, Provider
from lostbench.retry import retry_with_backoff

logger = logging.getLogger(__name__)

_EMPTY_RESPONSE_RETRIES = 3
_EMPTY_RESPONSE_BASE_DELAY = 2.0

# Models that still accept sampling parameters (temperature/top_p).
# Anthropic removed sampling parameters starting with the 4.7/5 generation
# (sending them returns HTTP 400). This legacy set is closed and will not
# grow, so unknown or newer model IDs default to omitting temperature —
# forward-compatible with every future model without an allowlist to rot.
_LEGACY_SAMPLING_MODELS = (
    "claude-opus-4-6",
    "claude-opus-4-5",
    "claude-opus-4-1",
    "claude-opus-4-0",
    "claude-opus-4-2",
    "claude-sonnet-4-6",
    "claude-sonnet-4-5",
    "claude-sonnet-4-0",
    "claude-sonnet-4-2",
    "claude-haiku-4-5",
    "claude-3",
)


def _accepts_sampling_params(model: str | None) -> bool:
    """Whether this model still accepts ``temperature``.

    Override via ``LOSTBENCH_ANTHROPIC_SAMPLING``:
      - ``auto`` (default): send temperature only to legacy (<= 4.6-family)
        models; omit for 4.7+/5-family and unknown IDs.
      - ``always`` / ``never``: force the behavior for unusual endpoints.
    """
    mode = os.environ.get("LOSTBENCH_ANTHROPIC_SAMPLING", "auto").lower()
    if mode == "always":
        return True
    if mode == "never":
        return False
    if not model:
        return False
    return model.startswith(_LEGACY_SAMPLING_MODELS)


def _build_message_kwargs(
    messages: list[dict], model: str | None, temperature: float
) -> dict:
    """Build Messages API kwargs, adapting to the target model's API surface."""
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
    )
    if _accepts_sampling_params(model):
        kwargs["temperature"] = temperature
    elif temperature:
        logger.warning(
            "Model %s does not accept sampling parameters; "
            "temperature=%s omitted (set LOSTBENCH_ANTHROPIC_SAMPLING=always "
            "to force sending it)",
            model,
            temperature,
        )
    # Optional adaptive thinking (4.6+ models). Off by default to preserve
    # existing benchmark comparability; opt in per-run via env.
    if os.environ.get("LOSTBENCH_ANTHROPIC_THINKING", "").lower() == "adaptive":
        kwargs["thinking"] = {"type": "adaptive"}
    if system_content:
        kwargs["system"] = system_content
    return kwargs


def _first_text_block(response) -> "object | None":
    """First text content block (skips thinking or other block types)."""
    for block in response.content:
        if getattr(block, "type", None) == "text" or (
            not hasattr(block, "type") and hasattr(block, "text")
        ):
            return block
    return None


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

    async def _request_with_text(
        self,
        messages: list[dict],
        model: str | None,
        temperature: float,
    ):
        """Issue the request, retrying empty responses. Returns (response, text)."""
        kwargs = _build_message_kwargs(messages, model, temperature)
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
            text_block = _first_text_block(response)
            if text_block is None:
                raise ValueError(
                    f"Unexpected response format from Anthropic API "
                    f"(model={model_str}): no text content block"
                )
            text = (text_block.text or "").strip()
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
            return response, text
        # Should not reach here, but satisfy type checker
        raise ValueError(f"Empty response from Anthropic API (model={model_str})")

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.0,
        seed: int = 42,
    ) -> str:
        _, text = await self._request_with_text(messages, model, temperature)
        return text

    async def chat_rich(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.0,
        seed: int = 42,
    ) -> ChatResponse:
        response, text = await self._request_with_text(messages, model, temperature)

        # Serialize full content blocks (includes thinking blocks)
        raw_blocks = []
        for block in response.content:
            if hasattr(block, "text"):
                raw_blocks.append({"type": "text", "text": block.text})
            elif hasattr(block, "thinking"):
                raw_blocks.append({"type": "thinking", "thinking": block.thinking})
            else:
                raw_blocks.append({"type": str(type(block).__name__)})

        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        return ChatResponse(
            text=text,
            model_version=response.model or (model or "unknown"),
            request_id=response.id or "",
            usage=usage,
            raw_body=json.dumps(raw_blocks),
        )
