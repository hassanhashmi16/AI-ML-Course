"""Resilience primitives for LLM calls: retry, circuit breaker, rate limiting.

Import these into any project that calls an LLM API. The retry decorator needs
tenacity; everything else is standard library only.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import Enum
from typing import Any, Callable

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)

logger = logging.getLogger(__name__)

# Network errors that can plausibly succeed on a second attempt.
TRANSIENT_ERRORS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.RemoteProtocolError,
)


def llm_retry(max_attempts: int = 4, max_wait: float = 30.0,
              retryable: tuple = TRANSIENT_ERRORS, wait=None):
    """Retry a function on transient errors with exponential backoff + jitter.

    Permanent errors (401, invalid request, ValueError) are not in `retryable`,
    so they propagate immediately instead of being retried.
    """
    if wait is None:
        wait = wait_exponential(multiplier=1, min=2, max=max_wait) + wait_random(0, 2)
    return retry(
        retry=retry_if_exception_type(retryable),
        stop=stop_after_attempt(max_attempts),
        wait=wait,
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )


class CircuitOpenError(Exception):
    """Raised when the breaker is open and calls fail fast."""


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Fails fast after N failures, lets one trial through after a cooldown."""

    def __init__(self, failure_threshold: int = 5, cooldown: float = 60.0):
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.opened_at = 0.0

    def call(self, fn: Callable) -> Any:
        if self.state is CircuitState.OPEN:
            if time.monotonic() - self.opened_at >= self.cooldown:
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitOpenError("circuit open: provider marked down")

        try:
            result = fn()
        except Exception:
            self._record_failure()
            raise
        self._record_success()
        return result

    def _record_failure(self) -> None:
        self.failures += 1
        if self.state is CircuitState.HALF_OPEN or self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()

    def _record_success(self) -> None:
        self.failures = 0
        self.state = CircuitState.CLOSED


class RateLimiter:
    """Caps concurrent in-flight calls with an asyncio semaphore."""

    def __init__(self, max_concurrency: int = 8):
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def __aenter__(self):
        await self._semaphore.acquire()

    async def __aexit__(self, *exc):
        self._semaphore.release()

    @staticmethod
    def retry_after_seconds(headers: dict) -> float:
        """Parse a Retry-After header (seconds or HTTP date) into seconds."""
        value = headers.get("Retry-After")
        if value is None:
            return 0.0
        if str(value).isdigit():
            return float(value)
        parsed = parsedate_to_datetime(value)
        return max(0.0, (parsed - datetime.now(timezone.utc)).total_seconds())


# Per-1M-token USD prices (input, output). Dated snapshot — prices change.
# Correct as of September 2026; replace with a live lookup in production.
PRICES_PER_1M = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-opus-4-8": (15.0, 75.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
}


def count_tokens(model: str, messages: list) -> int:
    """Count input tokens for `messages` using the model's tokenizer."""
    import litellm  # lazy import: keep this module usable without litellm
    return litellm.token_counter(model=model, messages=messages)


def estimate_cost(model: str, input_tokens: int, output_tokens: int = 0) -> float:
    """Estimate USD cost from a dated price table. Estimates only, not billing."""
    in_price, out_price = PRICES_PER_1M.get(model, (0.0, 0.0))
    return (input_tokens / 1_000_000 * in_price) + (output_tokens / 1_000_000 * out_price)
