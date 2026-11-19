import json
from typing import Any

import httpx
import pytest

from steamy_boy.config import ModelSettings
from steamy_boy.llm.openai_compatible import ModelOutputError, OpenAICompatibleModel
from steamy_boy.llm.types import Message, ToolCall, ToolSpec
from steamy_boy.retry import RetryableError

LOOKUP = ToolSpec(
    name="lookup",
    description="Look something up.",
    parameters={"type": "object", "properties": {"q": {"type": "string"}}},
)


def settings(**overrides: Any) -> ModelSettings:
    fields: dict[str, Any] = {
        "base_url": "https://models.example/api/v1/",
        "name": "some/model",
        "api_key": "sk-test",
        "input_usd_per_mtok": 3.0,
        "output_usd_per_mtok": 15.0,
    }
    return ModelSettings(**(fields | overrides))


def model_with(
    status: int = 200, body: object = None, headers: dict[str, str] | None = None, **overrides: Any
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, json=body if body is not None else {}, headers=headers)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleModel(settings(**overrides), http), requests


def completion(message: dict[str, Any], prompt_tokens: int = 1000, completion_tokens: int = 200):
    return {
        "model": "some/model-2026",
        "choices": [{"message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }


def test_sends_messages_and_tools_in_the_openai_format():
    model, requests = model_with(body=completion({"content": "hi"}))
    history = [
        Message.system("Be brief."),
        Message.user("Question?"),
        Message(
            role="assistant",
            tool_calls=[ToolCall(id="c1", name="lookup", arguments='{"q": "x"}')],
        ),
        Message.tool_result("c1", '{"rows": []}'),
    ]

    model.complete(history, [LOOKUP])

    request = requests[0]
    assert str(request.url) == "https://models.example/api/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer sk-test"
    body = json.loads(request.content)
    assert body["model"] == "some/model"
    assert body["messages"] == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Question?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": '{"q": "x"}'},
                }
            ],
        },
        {"role": "tool", "content": '{"rows": []}', "tool_call_id": "c1"},
    ]
    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "Look something up.",
                "parameters": LOOKUP.parameters,
            },
        }
    ]


def test_omits_tools_and_auth_when_there_are_none():
    model, requests = model_with(body=completion({"content": "hi"}), api_key=None)

    model.complete([Message.user("hi")], [])

    assert "tools" not in json.loads(requests[0].content)
    assert "Authorization" not in requests[0].headers


def test_parses_a_text_answer_with_usage_and_cost():
    model, _ = model_with(body=completion({"content": "The answer."}))

    response = model.complete([Message.user("q")], [])

    assert response.text == "The answer."
    assert response.tool_calls == []
    assert response.model == "some/model-2026"
    assert (response.usage.input_tokens, response.usage.output_tokens) == (1000, 200)
    assert response.cost_usd == pytest.approx((1000 * 3.0 + 200 * 15.0) / 1_000_000)
    assert response.latency_seconds >= 0


def test_parses_tool_calls_keeping_arguments_as_raw_json():
    message = {
        "content": None,
        "tool_calls": [
            {
                "id": "call_9",
                "type": "function",
                "function": {"name": "lookup", "arguments": '{"q": "playtime"}'},
            }
        ],
    }
    model, _ = model_with(body=completion(message))

    response = model.complete([Message.user("q")], [LOOKUP])

    assert response.text is None
    assert response.tool_calls == [
        ToolCall(id="call_9", name="lookup", arguments='{"q": "playtime"}')
    ]
    assert response.as_message().tool_calls == response.tool_calls


def test_local_models_cost_nothing():
    model, _ = model_with(
        body=completion({"content": "ok"}), input_usd_per_mtok=0, output_usd_per_mtok=0
    )

    assert model.complete([Message.user("q")], []).cost_usd == 0


def test_rate_limit_is_retryable_with_retry_after():
    model, _ = model_with(status=429, headers={"Retry-After": "7"})

    with pytest.raises(RetryableError) as raised:
        model.complete([Message.user("q")], [])

    assert raised.value.retry_after == 7.0


@pytest.mark.parametrize("status", [500, 502, 503])
def test_server_errors_are_retryable(status):
    model, _ = model_with(status=status)

    with pytest.raises(RetryableError):
        model.complete([Message.user("q")], [])


def test_connection_errors_are_retryable():
    """For example, a local Ollama that isn't running."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    model = OpenAICompatibleModel(settings(), httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(RetryableError):
        model.complete([Message.user("q")], [])


@pytest.mark.parametrize("status", [400, 401, 404])
def test_client_errors_are_not_retryable(status):
    model, _ = model_with(status=status)

    with pytest.raises(httpx.HTTPStatusError):
        model.complete([Message.user("q")], [])


def test_a_response_without_choices_is_an_error():
    model, _ = model_with(body={"choices": []})

    with pytest.raises(ModelOutputError):
        model.complete([Message.user("q")], [])
