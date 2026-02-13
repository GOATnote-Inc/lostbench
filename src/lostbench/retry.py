"""Retry logic for transient API errors."""

import asyncio
import sys

import openai
import anthropic


RETRYABLE_EXCEPTIONS = (
    openai.RateLimitError,
    openai.InternalServerError,
    openai.APIConnectionError,
    openai.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
)

MAX_RETRIES = 3
BASE_DELAY = 1.0
MAX_DELAY = 60.0


def _is_retryable_status(exc: Exception) -> bool:
    if isinstance(exc, (openai.APIStatusError, anthropic.APIStatusError)):
        return exc.status_code in (429, 500, 502, 503, 504, 529)
    return False


async def retry_with_backoff(coro_factory, *, max_retries: int = MAX_RETRIES):
    """Call coro_factory() with exponential backoff on transient failures.

    coro_factory is a zero-arg callable returning an awaitable (coroutines
    can't be re-awaited after failure).
    """
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except RETRYABLE_EXCEPTIONS as exc:
            if attempt == max_retries:
                raise
            delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
            print(
                f"  [retry] {type(exc).__name__} — attempt {attempt + 1}/{max_retries + 1}, "
                f"waiting {delay:.0f}s...",
                file=sys.stderr,
            )
            await asyncio.sleep(delay)
        except (openai.APIStatusError, anthropic.APIStatusError) as exc:
            if _is_retryable_status(exc) and attempt < max_retries:
                delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
                print(
                    f"  [retry] HTTP {exc.status_code} — attempt {attempt + 1}/{max_retries + 1}, "
                    f"waiting {delay:.0f}s...",
                    file=sys.stderr,
                )
                await asyncio.sleep(delay)
            else:
                raise
