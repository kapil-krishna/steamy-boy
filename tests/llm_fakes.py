"""A fake `ChatModel` for tests: replays scripted replies and records what it was sent."""

from steamy_boy.llm.types import Message, ModelResponse, ToolCall, ToolSpec, Usage


class ScriptedModel:
    """Returns (or raises) each scripted item in turn, one per `complete` call."""

    def __init__(self, *script: ModelResponse | Exception, name: str = "fake-model") -> None:
        self._script = list(script)
        self._name = name
        self.calls: list[tuple[list[Message], list[ToolSpec]]] = []

    @property
    def name(self) -> str:
        return self._name

    def complete(self, messages: list[Message], tools: list[ToolSpec]) -> ModelResponse:
        self.calls.append((list(messages), list(tools)))
        if not self._script:
            raise AssertionError(f"{self._name} was called more times than scripted")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def answer(text: str, model: str = "fake-model") -> ModelResponse:
    """A final text answer."""
    return ModelResponse(text=text, model=model, usage=Usage(input_tokens=10, output_tokens=5))


def tool_call(name: str, arguments: str = "{}", call_id: str = "call_1") -> ModelResponse:
    """A reply asking for one tool."""
    return ModelResponse(
        tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)],
        model="fake-model",
        usage=Usage(input_tokens=10, output_tokens=5),
    )
