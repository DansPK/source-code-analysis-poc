"""Configuration from the environment and `.env`."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The tool's own files. Relative to the package, so this works from a source
# checkout and from an installed copy alike.
PACKAGE_ROOT = Path(__file__).resolve().parents[1]

# The user's files: configuration, clones, reports. The tool runs from inside other
# people's projects, so nothing is written relative to the current directory.
USER_DIR = Path.home() / ".ask"


def project_path(value: str) -> Path:
    """Resolve a configured path against the user directory, not the caller's."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else USER_DIR / path


class Settings(BaseSettings):
    # ~/.ask/.env configures the installed tool; a .env in the current directory
    # overrides it, which is what a source checkout uses.
    model_config = SettingsConfigDict(env_file=(USER_DIR / ".env", ".env"), extra="ignore")

    # Any OpenAI-compatible endpoint.
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # How much of the project reaches the prompt. The bound is the design -- see AGENTS.md.
    max_caller_depth: int = 2
    max_callee_depth: int = 2
    max_snippet_lines: int = 40

    temp_dir: str = str(USER_DIR / "temp")  # where Git clones land
    reports_dir: str = str(USER_DIR / "reports")
    semgrep_rules: str = str(PACKAGE_ROOT / "rules" / "semgrep")  # ships with the tool

    api_host: str = "127.0.0.1"
    api_port: int = 8000


def get_settings() -> Settings:
    return Settings()
