"""The model interface (D7, D15). Feature code depends on `ChatModel` and never on a
provider SDK or wire format.
"""

from typing import Protocol

from steamy_boy.llm.types import Message, ModelResponse, ToolSpec


class ChatModel(Protocol):
    """Anything that can answer a conversation, optionally asking for tools.

    Implementations raise `RetryableError` for transient failures (rate limits, 5xx,
    timeouts) and anything else for failures that won't fix themselves.
    """

    @property
    def name(self) -> str: ...

    def complete(self, messages: list[Message], tools: list[ToolSpec]) -> ModelResponse: ...
