"""Run Semgrep and hand back its raw JSON.

This module is the only place that knows how Semgrep is invoked;
`findings/parser.py` is the only place that knows what its output looks like.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from app.config.settings import project_path
from app.repository.file_filter import SKIP_DIRS
from app.scanners import ScannerError
from app.utils.logging import get_logger

logger = get_logger(__name__)

TIMEOUT_SECONDS = 600


def _command() -> list[str]:
    """Semgrep is a Python dependency here, so it may not be on PATH."""
    binary = shutil.which("semgrep")
    return [binary] if binary else [sys.executable, "-m", "semgrep"]


def _configs(configs: str) -> list[str]:
    """Split the configured list, and check that any local directory exists.

    A registry pack (`p/security-audit`) is passed through; a path is resolved and
    verified, because a typo there would otherwise silently scan with fewer rules.
    """
    resolved = []
    for config in (c.strip() for c in configs.split(",") if c.strip()):
        if config.startswith("p/") or config.startswith("r/"):
            resolved.append(config)
            continue
        path = project_path(config)
        if not path.exists():
            raise ScannerError(f"Semgrep rules not found: {path}")
        resolved.append(str(path))
    return resolved


def scan(root: Path, configs: str) -> dict:
    """Scan `root` with every configured ruleset, returning Semgrep's parsed JSON."""
    rulesets = _configs(configs)

    command = [
        *_command(), "scan", "--json", "--quiet",
        # Semgrep defaults to git-tracked files only and applies a built-in ignore
        # list that excludes tests/. We are scanning whatever the user pointed at,
        # so both defaults have to go or findings silently disappear.
        "--no-git-ignore", "--x-ignore-semgrepignore-files",
        # ...but turning those off also drops .gitignore, so Semgrep would walk
        # .venv and node_modules. Exclude the same directories the analyzer skips.
        *[arg for directory in sorted(SKIP_DIRS) for arg in ("--exclude", directory)],
        *[arg for ruleset in rulesets for arg in ("--config", ruleset)],
        str(root),
    ]
    logger.info("Running Semgrep on %s with %d ruleset(s)", root, len(rulesets))

    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=TIMEOUT_SECONDS
        )
    except FileNotFoundError as exc:
        raise ScannerError("Semgrep is not installed. Run `uv sync`.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ScannerError(f"Semgrep timed out after {TIMEOUT_SECONDS}s on {root}") from exc

    # Semgrep uses exit code 1 for "findings were reported"; 2 and above are failures.
    if result.returncode >= 2:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise ScannerError(f"Semgrep failed: {detail[-1] if detail else result.returncode}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ScannerError(f"Semgrep returned output that is not JSON: {exc}") from exc
