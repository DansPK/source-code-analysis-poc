"""Uploaded-archive input: a zip sent by an MCP client whose disk this server cannot see."""

import base64
import binascii
import hashlib
import io
import shutil
import zipfile
from pathlib import Path

from app.config.settings import project_path
from app.source import SourceError

# How far an archive may expand beyond the upload limit. Source code compresses about 5x;
# more than this is a zip bomb, not a project.
MAX_EXPANSION = 10


def unpack(archive: str, temp_dir: str, max_upload_mb: int) -> Path:
    """Extract a base64 zip into `temp_dir/uploads/<hash>/` and return that directory.

    The directory is named after the archive's hash, so a follow-up question that sends
    the same project again reuses the first extraction.
    """
    try:
        data = base64.b64decode(archive, validate=True)
    except binascii.Error as exc:
        raise SourceError("The uploaded archive is not valid base64.") from exc

    limit = max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise SourceError(
            f"The upload is {len(data) / 2**20:.1f} MB; this server accepts at most "
            f"{max_upload_mb} MB (MAX_UPLOAD_MB)."
        )

    dest = project_path(temp_dir) / "uploads" / hashlib.sha256(data).hexdigest()[:16]
    if dest.exists():
        return dest

    try:
        members = [m for m in zipfile.ZipFile(io.BytesIO(data)).infolist() if not m.is_dir()]
    except zipfile.BadZipFile as exc:
        raise SourceError("The upload is not a zip archive.") from exc
    if sum(m.file_size for m in members) > limit * MAX_EXPANSION:
        raise SourceError("The archive expands to far more than it weighs; refusing to unpack it.")

    # Unpack beside the destination and rename at the end, so an interrupted upload never
    # leaves a half-extracted project that a later request would reuse.
    staging = dest.with_name(f"{dest.name}.partial")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for member in members:
                target = (staging / member.filename).resolve()
                # "Zip slip": a member named ../../x or /etc/x must not land outside.
                if not target.is_relative_to(staging.resolve()):
                    raise SourceError(f"Unsafe path in the archive: {member.filename}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
        staging.rename(dest)
    except SourceError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    except OSError:
        shutil.rmtree(staging, ignore_errors=True)
        if not dest.exists():  # another request unpacking the same archive won the rename
            raise
    return dest
