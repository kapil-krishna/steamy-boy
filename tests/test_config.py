import pytest

from steamy_boy.config import DEFAULT_DATABASE_URL, Settings


def settings_from_env(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    """Settings from these environment variables only (no `.env` file)."""
    for key in ("DATABASE_URL", "AGENT_MODEL__BASE_URL", "AGENT_MODEL__NAME"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_defaults_to_the_local_docker_database_and_no_model(monkeypatch: pytest.MonkeyPatch):
    settings = settings_from_env(monkeypatch)

    assert settings.database_url == DEFAULT_DATABASE_URL
    assert settings.agent_model is None


def test_reads_nested_model_settings_with_double_underscores(monkeypatch: pytest.MonkeyPatch):
    settings = settings_from_env(
        monkeypatch,
        AGENT_MODEL__BASE_URL="http://localhost:11434/v1",
        AGENT_MODEL__NAME="local-model",
    )

    assert settings.agent_model is not None
    assert settings.agent_model.base_url == "http://localhost:11434/v1"
    assert settings.agent_model.api_key is None
    assert settings.agent_model.input_usd_per_mtok == 0


def test_api_key_is_hidden_from_reprs(monkeypatch: pytest.MonkeyPatch):
    settings = settings_from_env(
        monkeypatch,
        AGENT_MODEL__BASE_URL="https://openrouter.ai/api/v1",
        AGENT_MODEL__NAME="some/model",
        AGENT_MODEL__API_KEY="sk-or-secret",
    )

    assert "sk-or-secret" not in repr(settings)
