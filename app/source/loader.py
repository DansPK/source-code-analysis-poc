"""Entry point for source loading.

Git and local input converge here: after this, the pipeline cannot tell how the
code arrived.
"""

from app.config.settings import Settings
from app.models import Repository
from app.source import SourceError
from app.source.git_loader import clone
from app.source.local_loader import load_local


def load_source(repo: str | None, path: str | None, settings: Settings) -> Repository:
    if repo:
        return clone(repo, settings.temp_dir)
    if path:
        return load_local(path)
    raise SourceError("Provide either a Git URL or a local path.")
