"""App settings, read from environment variables and `.env` (like Spring's
`@ConfigurationProperties`). Nested settings use a double underscore:
`AGENT_MODEL__BASE_URL` sets `settings.agent_model.base_url`.
"""

from functools import cache

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = "postgresql://steamy_boy:steamy_boy@localhost:5432/steamy_boy"


class ModelSettings(BaseModel):
    """One model behind an OpenAI-compatible endpoint: OpenRouter, Ollama, LM Studio... (D15)."""

    base_url: str
    """e.g. `https://openrouter.ai/api/v1`, or `http://localhost:11434/v1` for Ollama."""
    name: str
    """The model ID as that endpoint knows it."""
    api_key: SecretStr | None = None
    """Not needed for local runners. `SecretStr` keeps it out of logs and reprs."""
    input_usd_per_mtok: float = 0.0
    """Price per million input tokens, for the cost record (R9). 0 for local models."""
    output_usd_per_mtok: float = 0.0
    timeout_seconds: float = 120.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", extra="ignore")

    database_url: str = DEFAULT_DATABASE_URL
    agent_model: ModelSettings | None = None
    """The model `/ask` uses. Required to answer questions; not needed for ingest."""
    agent_fallback_model: ModelSettings | None = None
    """Tried when the agent model keeps failing with transient errors (R20)."""


@cache
def get_settings() -> Settings:
    """Read the settings once and reuse them (`@cache` memoises the result)."""
    return Settings()
