"""An adapter for OpenAI-compatible chat endpoints (D15).

One adapter covers cloud and local models, because they all speak this format:
OpenRouter, Ollama, LM Studio, llama.cpp and vLLM. Choosing between them is config
(`ModelSettings`). It uses plain httpx rather than a provider SDK, so the wire format is
visible and the retry policy stays ours (the SDKs retry on their own).
"""

import time
from typing import Any

import httpx
from pydantic import BaseModel

from steamy_boy.config import ModelSettings
from steamy_boy.llm.types import Message, ModelResponse, ToolCall, ToolSpec, Usage
from steamy_boy.retry import RetryableError


class ModelOutputError(Exception):
    """The endpoint answered, but not in a shape we can use (for example no choices)."""


class OpenAICompatibleModel:
    """A `ChatModel` that POSTs to `{base_url}/chat/completions`. One call, no retries."""

    def __init__(self, settings: ModelSettings, http: httpx.Client | None = None) -> None:
        self._settings = settings
        self._http = http or httpx.Client(timeout=settings.timeout_seconds)

    @property
    def name(self) -> str:
        return self._settings.name

    def complete(self, messages: list[Message], tools: list[ToolSpec]) -> ModelResponse:
        body: dict[str, Any] = {
            "model": self._settings.name,
            "messages": [_to_wire_message(m) for m in messages],
        }
        if tools:
            body["tools"] = [_to_wire_tool(t) for t in tools]

        started = time.perf_counter()
        raw = self._post(body)
        latency = time.perf_counter() - started

        completion = _Completion.model_validate(raw)
        if not completion.choices:
            raise ModelOutputError(f"no choices in the response from {self.name}")
        reply = completion.choices[0].message
        usage = Usage(
            input_tokens=completion.usage.prompt_tokens,
            output_tokens=completion.usage.completion_tokens,
        )
        return ModelResponse(
            text=reply.content,
            tool_calls=[
                ToolCall(id=c.id, name=c.function.name, arguments=c.function.arguments)
                for c in reply.tool_calls or []
            ],
            model=completion.model or self.name,
            usage=usage,
            cost_usd=self._cost(usage),
            latency_seconds=latency,
        )

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = {}
        if self._settings.api_key is not None:
            headers["Authorization"] = f"Bearer {self._settings.api_key.get_secret_value()}"
        url = self._settings.base_url.rstrip("/") + "/chat/completions"
        try:
            response = self._http.post(url, json=body, headers=headers)
        except httpx.TransportError as error:  # timeouts, connection refused
            raise RetryableError(f"network error calling {self.name}: {error!r}") from error

        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableError(
                f"{self.name} returned HTTP {response.status_code}",
                retry_after=_retry_after_seconds(response),
            )
        response.raise_for_status()  # other 4xx: a bad request or key, so don't retry
        return response.json()

    def _cost(self, usage: Usage) -> float:
        s = self._settings
        return (
            usage.input_tokens * s.input_usd_per_mtok + usage.output_tokens * s.output_usd_per_mtok
        ) / 1_000_000


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


# --- Our types -> the wire format --------------------------------------------------------


def _to_wire_message(message: Message) -> dict[str, Any]:
    wire: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        wire["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id is not None:
        wire["tool_call_id"] = message.tool_call_id
    return wire


def _to_wire_tool(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


# --- The wire format -> our types (the validation boundary for model responses) ----------


class _WireFunction(BaseModel):
    name: str
    arguments: str = "{}"


class _WireToolCall(BaseModel):
    id: str
    function: _WireFunction


class _WireMessage(BaseModel):
    content: str | None = None
    tool_calls: list[_WireToolCall] | None = None


class _WireChoice(BaseModel):
    message: _WireMessage


class _WireUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0


class _Completion(BaseModel):
    model: str | None = None
    choices: list[_WireChoice] = []
    usage: _WireUsage = _WireUsage()
