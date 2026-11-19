"""Provider-neutral types for talking to a chat model with tools.

The agent loop only sees these. Each adapter translates them to and from its provider's
wire format, so swapping providers never touches the loop (R8).
"""

from typing import Any, Literal

from pydantic import BaseModel


class ToolSpec(BaseModel):
    """A tool as the model sees it: what it's for and what arguments it takes."""

    name: str
    description: str
    parameters: dict[str, Any]
    """JSON Schema for the arguments. Usually `SomeArgsModel.model_json_schema()`."""


class ToolCall(BaseModel):
    """The model asking us to run a tool."""

    id: str
    """Echoed back with the result, so the model can match results to calls."""
    name: str
    arguments: str
    """Raw JSON text, exactly as the model wrote it. It's untrusted model output, so the
    caller validates it (for example `ArgsModel.model_validate_json(call.arguments)`)."""


class Message(BaseModel):
    """One turn of the conversation."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] = []
    """Set on assistant messages that ask for tools."""
    tool_call_id: str | None = None
    """Set on tool messages: which call this is the result of."""

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role="user", content=content)

    @classmethod
    def tool_result(cls, tool_call_id: str, content: str) -> Message:
        return cls(role="tool", tool_call_id=tool_call_id, content=content)


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class ModelResponse(BaseModel):
    """One reply from the model: either tool calls to run, or a final text answer."""

    text: str | None = None
    tool_calls: list[ToolCall] = []
    model: str
    """The model that actually answered. With a fallback, this shows which one (R20)."""
    usage: Usage = Usage()
    cost_usd: float = 0.0
    latency_seconds: float = 0.0

    def as_message(self) -> Message:
        """This reply as an assistant message, to append to the conversation."""
        return Message(role="assistant", content=self.text, tool_calls=self.tool_calls)
