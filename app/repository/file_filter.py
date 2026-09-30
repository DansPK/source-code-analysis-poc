"""Which files are worth looking at."""

from collections.abc import Iterator
from pathlib import Path

SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "vendor", "dist", "build",
    ".cache", "__pycache__", ".pytest_cache", ".idea", ".mypy_cache",
    # Build output of other ecosystems: Maven/Gradle, .NET, JS frameworks, test coverage.
    "target", ".gradle", "obj", ".next", ".nuxt", "coverage", ".terraform",
    # Coding agents keep whole copies of the project here; scanning them doubles every finding.
    ".claude", ".kilo", ".worktrees",
}
MAX_FILE_BYTES = 1_000_000  # generated or vendored blobs, not hand-written source


def iter_files(root: Path) -> Iterator[Path]:
    """Every candidate file under `root`, skipping noise directories and huge files."""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if SKIP_DIRS & set(path.relative_to(root).parts):
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        yield path
