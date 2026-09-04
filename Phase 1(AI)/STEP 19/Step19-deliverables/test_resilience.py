"""Unit tests for Step 19 resilience primitives. No live network calls."""

import asyncio

import httpx
import pytest
from tenacity import wait_fixed

from resilience import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    RateLimiter,
    llm_retry,
)
from idempotent_tool import InMemoryDedupe, write_row


def test_llm_retry_retries_transient_then_succeeds():
    calls = {"n": 0}

    @llm_retry(max_attempts=4, wait=wait_fixed(0))
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("connection dropped")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_llm_retry_does_not_retry_permanent_error():
    calls = {"n": 0}

    @llm_retry(max_attempts=4, wait=wait_fixed(0))
    def bad():
        calls["n"] += 1
        raise ValueError("invalid input")   # not transient, not retryable

    with pytest.raises(ValueError):
        bad()
    assert calls["n"] == 1


def test_circuit_breaker_opens_and_fails_fast():
    breaker = CircuitBreaker(failure_threshold=3, cooldown=10.0)

    def down():
        raise RuntimeError("provider down")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            breaker.call(down)

    with pytest.raises(CircuitOpenError):
        breaker.call(down)   # open, cooldown not elapsed -> fail fast


def test_circuit_breaker_half_open_allows_trial():
    breaker = CircuitBreaker(failure_threshold=2, cooldown=0.0)

    def down():
        raise RuntimeError("provider down")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            breaker.call(down)

    assert breaker.call(lambda: "recovered") == "recovered"
    assert breaker.state is CircuitState.CLOSED


def test_rate_limiter_caps_concurrency():
    limiter = RateLimiter(max_concurrency=2)
    active = 0
    peak = 0

    async def worker():
        nonlocal active, peak
        async with limiter:
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1

    async def main():
        await asyncio.gather(*(worker() for _ in range(10)))

    asyncio.run(main())
    assert peak == 2


def test_retry_after_parses_seconds():
    assert RateLimiter.retry_after_seconds({"Retry-After": "5"}) == 5.0


def test_idempotent_write_row_runs_side_effect_once():
    store = InMemoryDedupe()
    calls = {"n": 0}

    def execute(table, row_id):
        calls["n"] += 1
        return f"inserted {table}:{row_id}"

    first = write_row(store, execute, "emails", 42)
    second = write_row(store, execute, "emails", 42)   # retry, same op

    assert first == second
    assert calls["n"] == 1
