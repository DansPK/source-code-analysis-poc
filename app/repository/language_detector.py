"""Language and framework detection.

Only Python is parsed into the code map (see AGENTS.md); other languages are still
listed so the report can say what the project contains.
"""

from pathlib import Path

from app.models import FileNode

EXTENSIONS = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".jsx": "javascript",
    ".tsx": "typescript", ".java": "java", ".go": "go", ".rb": "ruby", ".php": "php",
}

# Top-level import names that identify a web framework -- these bring external input in.
FRAMEWORKS = {"flask", "django", "fastapi", "starlette", "tornado", "bottle"}

# Files that are entry points regardless of what they import.
ENTRY_POINT_NAMES = {"main.py", "app.py", "wsgi.py", "asgi.py", "manage.py"}


def detect_language(path: Path) -> str:
    return EXTENSIONS.get(path.suffix.lower(), "unknown")


def detect_frameworks(nodes: dict[str, FileNode]) -> list[str]:
    found = {
        imported.split(".")[0]
        for node in nodes.values()
        for imported in node.imports
        if imported.split(".")[0] in FRAMEWORKS
    }
    return sorted(found)


def detect_entry_points(nodes: dict[str, FileNode]) -> list[str]:
    """Files where attacker-controlled input plausibly enters the application."""
    entry_points = [
        path
        for path, node in nodes.items()
        if Path(path).name in ENTRY_POINT_NAMES
        or any(imported.split(".")[0] in FRAMEWORKS for imported in node.imports)
    ]
    return sorted(entry_points)
