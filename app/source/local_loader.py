"""Local directory or single-file input."""

from pathlib import Path

from app.models import Repository
from app.source import SourceError


def load_local(path: str) -> Repository:
    """Resolve a local directory or file into a Repository.

    A single file still yields a directory root -- its parent -- with the file
    recorded in `single_file`, so the analyzer (M3) knows to look at only that one.
    """
    target = Path(path).expanduser()
    if not target.exists():
        raise SourceError(f"Path does not exist: {target}")

    target = target.resolve()
    if target.is_dir():
        return Repository(root=str(target))
    return Repository(root=str(target.parent), single_file=target.name)
