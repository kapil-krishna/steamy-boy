"""Retry a transient-failure-prone operation with exponential backoff and full jitter."""

import logging
import random as _random
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


class RetryableError(Exception):
    """Raised by an operation to signal a transient failure that is worth retrying.

    The Steam client raises this for HTTP 429, 5xx responses and timeouts. Any other
    exception means "don't retry".
    """

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        """Seconds the server asked us to wait (from a `Retry-After` header), if any."""


def call_with_retry[T](
    operation: Callable[[], T],
    *,
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
    random: Callable[[], float] = _random.random,
) -> T:
    """Call `operation` and return its result, retrying on `RetryableError`.

    Behaviour:
    - `max_attempts` is the total number of calls, including the first. It must be at
      least 1, otherwise raise `ValueError` without calling `operation`.
    - If `operation` raises `RetryableError` and attempts remain, sleep, then call again.
    - The delay before retry number n (n = 1 for the first retry) uses full jitter:
      `random() * min(max_delay, base_delay * 2 ** (n - 1))`.
    - If the error has a `retry_after`, sleep exactly that long instead.
    - When the last attempt fails, re-raise that `RetryableError` itself (not a wrapper).
      Don't sleep after the last attempt.
    - Any other exception propagates immediately, with no sleep and no retry.

    `sleep` and `random` are injected so tests can run instantly and deterministically.
    """

    if max_attempts < 1:
        raise ValueError("Max attempts must be greater than 0")

    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except RetryableError as e:
            if attempt >= max_attempts:
                raise

            if e.retry_after is not None:
                delay = e.retry_after
            else:
                delay = random() * min(max_delay, base_delay * 2 ** (attempt - 1))

            logger.warning(
                "Attempt %d of %d failed (%s), retrying in %.1fs", attempt, max_attempts, e, delay
            )

            sleep(delay)
