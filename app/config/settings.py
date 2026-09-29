"""Configuration from the environment and `.env`."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_path(value: str) -> Path:
    """Resolve a configured path against the project, not the caller's directory.

    The scanner is pointed at other people's code, so it is routinely run from
    somewhere else entirely.
    """
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Any OpenAI-compatible endpoint.
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # How much of the project reaches the prompt. The bound is the design -- see AGENTS.md.
    max_caller_depth: int = 2
    max_callee_depth: int = 2
    max_snippet_lines: int = 40

    temp_dir: str = "temp"  # where Git clones land
    semgrep_rules: str = "rules/semgrep"  # --config passed to Semgrep

    api_host: str = "127.0.0.1"
    api_port: int = 8000


def get_settings() -> Settings:
    return Settings()
