"""Retries and a fallback model around any `ChatModel` (R20)."""

import logging
import time
from collections.abc import Callable
from functools import partial

from steamy_boy.config import Settings
from steamy_boy.llm import ChatModel
from steamy_boy.llm.openai_compatible import OpenAICompatibleModel
from steamy_boy.llm.types import Message, ModelResponse, ToolSpec
from steamy_boy.retry import RetryableError, call_with_retry

logger = logging.getLogger(__name__)


class FallbackModel:
    """A `ChatModel` that retries transient failures, then tries a second model.

    Only transient failures (`RetryableError`: rate limits, 5xx, timeouts) are retried
    or passed to the fallback. Anything else, such as a 400 for a bad request or a 401
    for a bad key, is raised straight away: a second model wouldn't fix it.
    """

    def __init__(
        self,
        primary: ChatModel,
        fallback: ChatModel | None = None,
        *,
        max_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._max_attempts = max_attempts
        self._sleep = sleep

    @property
    def name(self) -> str:
        return self._primary.name

    def complete(self, messages: list[Message], tools: list[ToolSpec]) -> ModelResponse:
        try:
            return self._with_retry(self._primary, messages, tools)
        except RetryableError as error:
            if self._fallback is None:
                raise
            logger.warning(
                "%s failed after %d attempts (%s); using fallback %s",
                self._primary.name,
                self._max_attempts,
                error,
                self._fallback.name,
            )
            return self._with_retry(self._fallback, messages, tools)

    def _with_retry(
        self, model: ChatModel, messages: list[Message], tools: list[ToolSpec]
    ) -> ModelResponse:
        return call_with_retry(
            partial(model.complete, messages, tools),
            max_attempts=self._max_attempts,
            sleep=self._sleep,
        )


class ModelNotConfiguredError(Exception):
    pass


def build_agent_model(settings: Settings) -> ChatModel:
    """The agent's model from config: the primary, wrapped with retries and the fallback."""
    if settings.agent_model is None:
        raise ModelNotConfiguredError(
            "No agent model configured. Set AGENT_MODEL__BASE_URL and AGENT_MODEL__NAME "
            "(see .env.example)."
        )
    fallback = (
        OpenAICompatibleModel(settings.agent_fallback_model)
        if settings.agent_fallback_model is not None
        else None
    )
    return FallbackModel(OpenAICompatibleModel(settings.agent_model), fallback)
