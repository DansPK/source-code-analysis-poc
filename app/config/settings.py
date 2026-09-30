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
    max_ask_steps: int = 20  # tool calls the ask agent may make before it must answer

    temp_dir: str = str(WORKSPACE / "projects")  # where Git clones land
    reports_dir: str = str(WORKSPACE / "reports")
    # Comma-separated Semgrep configs. Registry packs cover every language Semgrep
    # supports -- `p/security-audit` alone finds nothing in many Java projects, so the
    # broader `p/default` and `p/owasp-top-ten` run too (Semgrep drops rules the packs
    # share). The bundled directory holds our own rules and stays last.
    semgrep_configs: str = (
        f"p/security-audit,p/default,p/owasp-top-ten,p/secrets,{PACKAGE_ROOT / 'rules' / 'semgrep'}"
    )

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # scan-mcp. Set MCP_HOST=0.0.0.0 to serve other machines -- and then set MCP_API_KEY.
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8001  # differs from api_port so both can run at once
    mcp_api_key: str = ""  # when set, every MCP request needs "Authorization: Bearer <key>"
    max_upload_mb: int = 100  # largest project archive an MCP client may upload


def get_settings() -> Settings:
    return Settings()
