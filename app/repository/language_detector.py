"""Language and framework detection.

Every language in `code_map.LANGUAGES` is parsed into the code map; the rest are still
listed so the report can say what the project contains.
"""

import re
from pathlib import Path

from app.models import FileNode

EXTENSIONS = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".cjs": "javascript", ".ts": "typescript", ".tsx": "typescript", ".java": "java",
    ".kt": "kotlin", ".kts": "kotlin", ".go": "go", ".rb": "ruby", ".php": "php",
    ".cs": "csharp", ".rs": "rust", ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp",
    ".hpp": "cpp", ".scala": "scala", ".swift": "swift", ".sh": "shell",
    ".tf": "terraform", ".sql": "sql",
}

# Imported module -> the web framework it belongs to. A file importing one of these is
# where external input comes in. Prefixes are chosen so only request-handling code
# matches: Spring's `web` package, not `org.springframework.data`, which a repository
# class imports too.
FRAMEWORKS = {
    "flask": "flask", "django": "django", "fastapi": "fastapi", "starlette": "starlette",
    "tornado": "tornado", "bottle": "bottle",
    "org.springframework.web": "spring", "javax.ws.rs": "jax-rs", "jakarta.ws.rs": "jax-rs",
    "javax.servlet": "servlet", "jakarta.servlet": "servlet", "io.ktor": "ktor",
    "express": "express", "koa": "koa", "fastify": "fastify", "@nestjs/common": "nestjs",
    "@hapi/hapi": "hapi", "next/server": "nextjs",
    "github.com/gin-gonic/gin": "gin", "github.com/labstack/echo": "echo",
    "github.com/gofiber/fiber": "fiber", "net/http": "net/http",
    "Illuminate\\Http": "laravel", "Illuminate\\Support\\Facades\\Route": "laravel",
    "Symfony\\Component\\HttpFoundation": "symfony",
    "Microsoft.AspNetCore": "aspnetcore", "System.Web": "aspnet",
    "sinatra": "sinatra", "actix_web": "actix", "axum": "axum", "rocket": "rocket",
    "Vapor": "vapor", "akka.http": "akka-http", "play.api.mvc": "play",
}

# Files that are entry points regardless of what they import.
ENTRY_POINT_NAMES = {
    "main.py", "app.py", "wsgi.py", "asgi.py", "manage.py",
    "server.js", "app.js", "index.js", "server.ts", "app.ts", "main.ts",
    "main.go", "Program.cs", "index.php", "config.ru",
}


def detect_language(path: Path) -> str:
    return EXTENSIONS.get(path.suffix.lower(), "unknown")


def _framework(imported: str) -> str | None:
    """`org.springframework.web.bind.annotation.GetMapping` -> 'spring'."""
    for module, framework in FRAMEWORKS.items():
        if re.match(rf"{re.escape(module)}($|[./\\:])", imported):
            return framework
    return None


def detect_frameworks(nodes: dict[str, FileNode]) -> list[str]:
    found = {_framework(imported) for node in nodes.values() for imported in node.imports}
    return sorted(found - {None})


def detect_entry_points(nodes: dict[str, FileNode]) -> list[str]:
    """Files where attacker-controlled input plausibly enters the application."""
    entry_points = [
        path
        for path, node in nodes.items()
        if Path(path).name in ENTRY_POINT_NAMES
        or any(_framework(imported) for imported in node.imports)
    ]
    return sorted(entry_points)
