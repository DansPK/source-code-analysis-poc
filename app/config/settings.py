"""Configuration from the environment and `.env`."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Any OpenAI-compatible endpoint. With llm_mock the pipeline runs without a key.
    llm_mock: bool = True
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # How much of the project reaches the prompt. The bound is the design -- see AGENTS.md.
    max_caller_depth: int = 2
    max_callee_depth: int = 2
    max_snippet_lines: int = 40

    temp_dir: str = "temp"  # where Git clones land


def get_settings() -> Settings:
    return Settings()
