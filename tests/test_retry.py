from collections.abc import Callable
from typing import Any

import pytest

from steamy_boy.retry import RetryableError, call_with_retry


class FakeOperation:
    """Raises the queued exceptions in order, then returns `result` on every later call."""

    def __init__(self, *errors: Exception, result: str = "ok") -> None:
        self._errors = list(errors)
        self._result = result
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        return self._result


class RecordingSleep:
    """Stands in for `time.sleep`: records each delay instead of waiting."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


@pytest.fixture
def sleep() -> RecordingSleep:
    return RecordingSleep()


def half() -> float:
    """A fixed `random()` so jittered delays are predictable: exactly half the cap."""
    return 0.5


def retryable() -> RetryableError:
    return RetryableError("HTTP 429")


def run(operation: Callable[[], str], sleep: RecordingSleep, **kwargs: Any) -> str:
    return call_with_retry(operation, sleep=sleep, random=half, **kwargs)


def test_returns_result_without_sleeping_when_first_call_succeeds(sleep):
    operation = FakeOperation()

    assert run(operation, sleep) == "ok"
    assert operation.calls == 1
    assert sleep.delays == []


def test_retries_until_success(sleep):
    operation = FakeOperation(retryable(), retryable())

    assert run(operation, sleep) == "ok"
    assert operation.calls == 3


def test_delays_grow_exponentially_with_full_jitter(sleep):
    operation = FakeOperation(retryable(), retryable(), retryable())

    run(operation, sleep, base_delay=1.0)

    # caps are 1, 2, 4; random() = 0.5 takes half of each
    assert sleep.delays == [0.5, 1.0, 2.0]


def test_delay_cap_is_limited_by_max_delay(sleep):
    operation = FakeOperation(*[retryable() for _ in range(4)])

    run(operation, sleep, base_delay=1.0, max_delay=4.0)

    # caps are 1, 2, 4, then 8 limited to 4
    assert sleep.delays == [0.5, 1.0, 2.0, 2.0]


def test_gives_up_after_max_attempts_and_reraises_the_last_error(sleep):
    first, second, last = RetryableError("1"), RetryableError("2"), RetryableError("3")
    operation = FakeOperation(first, second, last)

    with pytest.raises(RetryableError) as raised:
        run(operation, sleep, max_attempts=3)

    assert raised.value is last
    assert operation.calls == 3
    assert len(sleep.delays) == 2  # no sleep after the final attempt


def test_non_retryable_error_propagates_immediately(sleep):
    operation = FakeOperation(ValueError("bad response"))

    with pytest.raises(ValueError, match="bad response"):
        run(operation, sleep)

    assert operation.calls == 1
    assert sleep.delays == []


def test_retry_after_overrides_the_computed_delay(sleep):
    operation = FakeOperation(RetryableError("HTTP 429", retry_after=7.0))

    run(operation, sleep)

    assert sleep.delays == [7.0]


@pytest.mark.parametrize("max_attempts", [0, -1])
def test_rejects_max_attempts_below_one_without_calling(sleep, max_attempts):
    operation = FakeOperation()

    with pytest.raises(ValueError):
        run(operation, sleep, max_attempts=max_attempts)

    assert operation.calls == 0
