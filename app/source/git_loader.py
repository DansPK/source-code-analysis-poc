"""Git URL input."""

import re
import shutil
from pathlib import Path

from git import GitCommandError, Repo

from app.models import Repository
from app.source import SourceError


def _workspace(url: str, temp_dir: str) -> Path:
    """Directory to clone into, named after the repository."""
    name = re.sub(r"[^A-Za-z0-9._-]", "_", url.rstrip("/").split("/")[-1].removesuffix(".git"))
    return Path(temp_dir) / (name or "repo")


def clone(url: str, temp_dir: str) -> Repository:
    """Shallow-clone `url` into `temp_dir`, replacing any previous clone."""
    dest = _workspace(url, temp_dir)
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        Repo.clone_from(url, dest, depth=1)
    except GitCommandError as exc:
        # GitPython wraps stderr as "\n  stderr: '...'", so show the git line that matters.
        lines = [line.strip().strip("'") for line in (exc.stderr or "").splitlines() if line.strip()]
        detail = next((l for l in lines if l.startswith("fatal:")), lines[-1] if lines else str(exc))
        raise SourceError(f"Could not clone {url}: {detail}") from exc

    return Repository(root=str(dest.resolve()), origin=url)
