"""Tests for retry logic and circuit breaker."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import openai
import anthropic

from lostbench.retry import (
    retry_with_backoff,
    reset_circuit_breaker,
    CircuitOpenError,
    _circuit_breaker,
    CIRCUIT_BREAKER_THRESHOLD,
)


class TestRetryWithBackoff:
    def test_succeeds_first_attempt(self):
        mock = AsyncMock(return_value="ok")
        result = asyncio.run(retry_with_backoff(mock))
        assert result == "ok"
        assert mock.call_count == 1

    def test_retries_on_rate_limit(self):
        mock = AsyncMock(side_effect=[
            openai.RateLimitError(
                message="rate limited",
                response=AsyncMock(status_code=429, headers={}),
                body=None,
            ),
            "ok",
        ])
        with patch("lostbench.retry.asyncio.sleep", new_callable=AsyncMock):
            result = asyncio.run(retry_with_backoff(mock))
        assert result == "ok"
        assert mock.call_count == 2

    def test_exhausts_retries(self):
        exc = openai.RateLimitError(
            message="rate limited",
            response=AsyncMock(status_code=429, headers={}),
            body=None,
        )
        mock = AsyncMock(side_effect=exc)
        with patch("lostbench.retry.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(openai.RateLimitError):
                asyncio.run(retry_with_backoff(mock, max_retries=2))
        assert mock.call_count == 3  # initial + 2 retries

    def test_no_retry_on_auth_error(self):
        exc = openai.AuthenticationError(
            message="bad key",
            response=AsyncMock(status_code=401, headers={}),
            body=None,
        )
        mock = AsyncMock(side_effect=exc)
        with pytest.raises(openai.AuthenticationError):
            asyncio.run(retry_with_backoff(mock))
        assert mock.call_count == 1

    def test_retries_anthropic_rate_limit(self):
        mock = AsyncMock(side_effect=[
            anthropic.RateLimitError(
                message="rate limited",
                response=AsyncMock(status_code=429, headers={}),
                body=None,
            ),
            "ok",
        ])
        with patch("lostbench.retry.asyncio.sleep", new_callable=AsyncMock):
            result = asyncio.run(retry_with_backoff(mock))
        assert result == "ok"
        assert mock.call_count == 2

    def test_backoff_delays_are_exponential(self):
        exc = openai.RateLimitError(
            message="rate limited",
            response=AsyncMock(status_code=429, headers={}),
            body=None,
        )
        mock = AsyncMock(side_effect=[exc, exc, "ok"])
        sleep_mock = AsyncMock()
        with patch("lostbench.retry.asyncio.sleep", sleep_mock):
            result = asyncio.run(retry_with_backoff(mock))
        assert result == "ok"
        delays = [call.args[0] for call in sleep_mock.call_args_list]
        assert delays == [1.0, 2.0]


class TestCircuitBreaker:
    """Circuit breaker prevents retry storms during persistent outages."""

    def setup_method(self):
        reset_circuit_breaker()

    def teardown_method(self):
        reset_circuit_breaker()

    def test_circuit_opens_after_threshold(self):
        """After N consecutive failures, circuit opens and raises immediately."""
        exc = openai.RateLimitError(
            message="rate limited",
            response=AsyncMock(status_code=429, headers={}),
            body=None,
        )
        mock = AsyncMock(side_effect=exc)

        # Exhaust retries repeatedly until circuit opens
        with patch("lostbench.retry.asyncio.sleep", new_callable=AsyncMock):
            for _ in range(2):  # 2 calls * (1 + 3 retries) = 8 failures > threshold of 5
                with pytest.raises(openai.RateLimitError):
                    asyncio.run(retry_with_backoff(mock, max_retries=3))

        # Circuit should now be open
        assert _circuit_breaker.is_open
        with pytest.raises(CircuitOpenError):
            asyncio.run(retry_with_backoff(AsyncMock(return_value="ok")))

    def test_circuit_resets_on_success(self):
        """A successful call resets the failure counter."""
        exc = openai.RateLimitError(
            message="rate limited",
            response=AsyncMock(status_code=429, headers={}),
            body=None,
        )
        # Fail a few times then succeed
        mock = AsyncMock(side_effect=[exc, exc, "ok"])
        with patch("lostbench.retry.asyncio.sleep", new_callable=AsyncMock):
            result = asyncio.run(retry_with_backoff(mock))
        assert result == "ok"
        assert not _circuit_breaker.is_open

    def test_reset_circuit_breaker(self):
        """Manual reset clears the circuit."""
        for _ in range(CIRCUIT_BREAKER_THRESHOLD):
            _circuit_breaker.record_failure()
        assert _circuit_breaker.is_open
        reset_circuit_breaker()
        assert not _circuit_breaker.is_open
