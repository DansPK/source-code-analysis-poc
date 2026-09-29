"""Configuration from the environment and `.env`."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parents[1]  # app/
PROJECT_ROOT = PACKAGE_ROOT.parent

# Everything this tool writes goes here: clones, reports and saved conversations.
# Nothing is written outside the checkout, and nothing into the project being
# examined.
WORKSPACE = PROJECT_ROOT / "workspace"


def project_path(value: str) -> Path:
    """Resolve a configured path against the workspace, not the caller's directory."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else WORKSPACE / path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    # Any OpenAI-compatible endpoint.
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # How much of the project reaches the prompt. The bound is the design -- see AGENTS.md.
    max_caller_depth: int = 2
    max_callee_depth: int = 2
    max_snippet_lines: int = 40

    temp_dir: str = str(WORKSPACE / "projects")  # where Git clones land
    reports_dir: str = str(WORKSPACE / "reports")
    # Comma-separated Semgrep configs. Registry packs cover every language Semgrep
    # supports; the bundled directory holds our own rules.
    semgrep_configs: str = f"p/security-audit,p/secrets,{PACKAGE_ROOT / 'rules' / 'semgrep'}"

    api_host: str = "127.0.0.1"
    api_port: int = 8000


def get_settings() -> Settings:
    return Settings()
