"""Entry point for source loading.

Git, uploaded and local input converge here: after this, the pipeline cannot tell how
the code arrived.
"""

from pathlib import Path

from app.config.settings import Settings
from app.models import Repository
from app.source import SourceError
from app.source.archive_loader import unpack
from app.source.git_loader import clone
from app.source.local_loader import load_local


def load_source(
    repo: str | None,
    path: str | None,
    settings: Settings,
    *,
    branch: str | None = None,
    archive: str | None = None,
    subpath: str | None = None,
) -> Repository:
    """`archive` is a base64 zip, for a client that shares no disk with this process.
    `subpath` narrows a clone or an archive to one folder or file inside it."""
    if repo:
        repository = _narrow(Path(clone(repo, settings.temp_dir, branch).root), subpath)
        repository.origin = repo
        return repository
    if archive:
        return _narrow(unpack(archive, settings.temp_dir, settings.max_upload_mb), subpath)
    if path:
        return load_local(path)
    raise SourceError("Provide a Git URL, an uploaded archive or a local path.")


def _narrow(root: Path, subpath: str | None) -> Repository:
    if not subpath:
        return load_local(str(root))
    target = (root / subpath).resolve()
    if not target.is_relative_to(root.resolve()):
        raise SourceError(f"{subpath} is outside the project.")
    return load_local(str(target))
