"""Retry logic for transient API errors with circuit breaker."""

import asyncio
import logging
import threading

import openai
import anthropic

logger = logging.getLogger(__name__)


RETRYABLE_EXCEPTIONS = (
    openai.RateLimitError,
    openai.InternalServerError,
    openai.APIConnectionError,
    openai.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    TimeoutError,
)

MAX_RETRIES = 3
BASE_DELAY = 1.0
MAX_DELAY = 60.0
CIRCUIT_BREAKER_THRESHOLD = 5


class CircuitBreaker:
    """Fail-fast after consecutive transient failures across requests.

    Thread-safe. Shared across all retry_with_backoff calls so that
    persistent provider outages are detected quickly rather than burning
    through per-request retry budgets.
    """

    def __init__(self, threshold: int = CIRCUIT_BREAKER_THRESHOLD) -> None:
        self._threshold = threshold
        self._consecutive_failures = 0
        self._lock = threading.Lock()

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._consecutive_failures >= self._threshold

    def reset(self) -> None:
        with self._lock:
            self._consecutive_failures = 0


# Module-level shared instance
_circuit_breaker = CircuitBreaker()


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open (too many consecutive failures)."""


def _is_retryable_status(exc: Exception) -> bool:
    if isinstance(exc, (openai.APIStatusError, anthropic.APIStatusError)):
        return exc.status_code in (429, 500, 502, 503, 504, 529)
    return False


async def retry_with_backoff(coro_factory, *, max_retries: int = MAX_RETRIES):
    """Call coro_factory() with exponential backoff on transient failures.

    coro_factory is a zero-arg callable returning an awaitable (coroutines
    can't be re-awaited after failure).

    Raises CircuitOpenError if too many consecutive failures have occurred
    across all callers, indicating a persistent provider outage.
    """
    if _circuit_breaker.is_open:
        raise CircuitOpenError(
            f"Circuit breaker open after {CIRCUIT_BREAKER_THRESHOLD} consecutive "
            f"failures — provider appears down. Call retry.reset_circuit_breaker() "
            f"to retry."
        )

    for attempt in range(max_retries + 1):
        try:
            result = await coro_factory()
            _circuit_breaker.record_success()
            return result
        except RETRYABLE_EXCEPTIONS as exc:
            _circuit_breaker.record_failure()
            if attempt == max_retries:
                raise
            delay = min(BASE_DELAY * (2**attempt), MAX_DELAY)
            logger.warning(
                "%s — attempt %d/%d, waiting %.0fs...",
                type(exc).__name__,
                attempt + 1,
                max_retries + 1,
                delay,
            )
            await asyncio.sleep(delay)
        except (openai.APIStatusError, anthropic.APIStatusError) as exc:
            if _is_retryable_status(exc) and attempt < max_retries:
                _circuit_breaker.record_failure()
                delay = min(BASE_DELAY * (2**attempt), MAX_DELAY)
                logger.warning(
                    "HTTP %d — attempt %d/%d, waiting %.0fs...",
                    exc.status_code,
                    attempt + 1,
                    max_retries + 1,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                if _is_retryable_status(exc):
                    _circuit_breaker.record_failure()
                raise


def reset_circuit_breaker() -> None:
    """Reset the shared circuit breaker (e.g. between eval runs)."""
    _circuit_breaker.reset()
