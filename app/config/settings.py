"""Configuration loaded from the environment and `.env`.

Every tunable the pipeline has lives here. Modules take a `Settings` argument
rather than reading the environment themselves, so tests can pass their own.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM ---------------------------------------------------------------
    # Any OpenAI-compatible endpoint. With mock=True no key is needed and the
    # pipeline runs end to end against canned responses.
    llm_mock: bool = True
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # --- Context bounds ----------------------------------------------------
    # These cap how much of the project reaches the prompt. The bound is the
    # design, not a tuning knob -- see AGENTS.md before raising them.
    max_caller_depth: int = 2
    max_callee_depth: int = 2
    max_snippet_lines: int = 40

    # --- Paths -------------------------------------------------------------
    temp_dir: str = "temp"
    reports_dir: str = "reports"
    semgrep_rules_dir: str = "rules/semgrep"

    # --- Scanning ----------------------------------------------------------
    max_file_size_bytes: int = 1_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
