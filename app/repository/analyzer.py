"""Whole-project analysis (spec §5.2): what is here, and how it connects."""

from pathlib import Path

from app.models import CodeMap, Repository, SourceFile
from app.repository.code_map import build_code_map
from app.repository.file_filter import iter_files
from app.repository.language_detector import (
    detect_entry_points,
    detect_frameworks,
    detect_language,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


def analyze(repository: Repository) -> CodeMap:
    """Fill in `repository` (files, languages, frameworks, entry points) and map the code.

    When `repository.single_file` is set the user asked to scan one file, so only that
    file is analyzed even though the root is its directory.
    """
    root = Path(repository.root)
    if repository.single_file:
        paths = [root / repository.single_file]
    else:
        paths = list(iter_files(root))

    repository.files = [
        SourceFile(path=str(path.relative_to(root)), language=detect_language(path))
        for path in paths
    ]
    repository.languages = sorted(
        {f.language for f in repository.files if f.language != "unknown"}
    )

    python_files = [f.path for f in repository.files if f.language == "python"]
    code_map = build_code_map(root, python_files)

    repository.frameworks = detect_frameworks(code_map.files)
    repository.entry_points = detect_entry_points(code_map.files)

    logger.info(
        "Analyzed %d files (%d Python), frameworks=%s, entry points=%d",
        len(repository.files),
        len(python_files),
        repository.frameworks or "none",
        len(repository.entry_points),
    )
    return code_map
