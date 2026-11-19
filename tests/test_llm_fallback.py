import httpx
import pytest
from llm_fakes import ScriptedModel, answer

from steamy_boy.config import ModelSettings, Settings
from steamy_boy.llm.fallback import FallbackModel, ModelNotConfiguredError, build_agent_model
from steamy_boy.llm.types import Message
from steamy_boy.retry import RetryableError

QUESTION = [Message.user("q")]


def no_sleep(_: float) -> None:
    pass


def overloaded() -> RetryableError:
    return RetryableError("HTTP 503")


def test_uses_the_primary_when_it_works():
    primary = ScriptedModel(answer("from primary", model="primary"))
    fallback = ScriptedModel(name="fallback")

    response = FallbackModel(primary, fallback, sleep=no_sleep).complete(QUESTION, [])

    assert response.model == "primary"
    assert fallback.calls == []


def test_retries_the_primary_before_giving_up_on_it():
    primary = ScriptedModel(overloaded(), answer("second try", model="primary"))

    response = FallbackModel(primary, sleep=no_sleep).complete(QUESTION, [])

    assert response.text == "second try"
    assert len(primary.calls) == 2


def test_falls_back_after_the_primary_keeps_failing():
    """R20: the answer comes from the fallback, and the response says which model."""
    primary = ScriptedModel(overloaded(), overloaded(), overloaded(), name="primary")
    fallback = ScriptedModel(answer("from fallback", model="fallback"), name="fallback")

    response = FallbackModel(primary, fallback, max_attempts=3, sleep=no_sleep).complete(
        QUESTION, []
    )

    assert response.model == "fallback"
    assert len(primary.calls) == 3


def test_a_non_transient_error_is_not_retried_or_passed_to_the_fallback():
    request = httpx.Request("POST", "https://models.example")
    bad_request = httpx.HTTPStatusError(
        "400", request=request, response=httpx.Response(400, request=request)
    )
    primary = ScriptedModel(bad_request)
    fallback = ScriptedModel(name="fallback")

    with pytest.raises(httpx.HTTPStatusError):
        FallbackModel(primary, fallback, sleep=no_sleep).complete(QUESTION, [])

    assert len(primary.calls) == 1
    assert fallback.calls == []


def test_without_a_fallback_the_last_error_is_raised():
    primary = ScriptedModel(overloaded(), overloaded())

    with pytest.raises(RetryableError):
        FallbackModel(primary, max_attempts=2, sleep=no_sleep).complete(QUESTION, [])


def test_build_agent_model_needs_an_agent_model_configured():
    with pytest.raises(ModelNotConfiguredError):
        build_agent_model(Settings(_env_file=None))  # type: ignore[call-arg]


def test_build_agent_model_from_settings():
    local = ModelSettings(base_url="http://localhost:11434/v1", name="local-model")

    model = build_agent_model(Settings(_env_file=None, agent_model=local))  # type: ignore[call-arg]

    assert model.name == "local-model"
