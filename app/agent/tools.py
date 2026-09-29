"""The actions the ask agent can take on a project.

Each tool takes plain arguments and returns text. Output is truncated, because
everything returned here goes back into the next prompt.
"""

import re
from pathlib import Path

from app.models import CodeMap, Repository

MAX_LINES = 200
MAX_MATCHES = 40


def _truncate(lines: list[str], limit: int = MAX_LINES) -> str:
    if len(lines) > limit:
        lines = lines[:limit] + [f"... {len(lines) - limit} more lines omitted"]
    return "\n".join(lines)


def list_files(repository: Repository, **_) -> str:
    return _truncate([f"{f.path} ({f.language})" for f in repository.files])


def read_file(repository: Repository, path: str = "", start: int = 1, end: int = 0, **_) -> str:
    target = Path(repository.root) / path
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return f"Cannot read {path}: {exc}"

    end = end or len(lines)
    selected = lines[max(0, start - 1) : end]
    numbered = [f"{i:>5}  {line}" for i, line in enumerate(selected, start=max(1, start))]
    return _truncate(numbered)


def search(repository: Repository, pattern: str = "", **_) -> str:
    """Regex search across the project's source files."""
    try:
        expression = re.compile(pattern)
    except re.error as exc:
        return f"Invalid pattern: {exc}"

    root = Path(repository.root)
    matches = []
    for source_file in repository.files:
        try:
            lines = (root / source_file.path).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(lines, start=1):
            if expression.search(line):
                matches.append(f"{source_file.path}:{number}: {line.strip()[:160]}")
                if len(matches) >= MAX_MATCHES:
                    return _truncate(matches) + f"\n... stopped at {MAX_MATCHES} matches"
    return _truncate(matches) if matches else f"No match for {pattern!r}"


def find_symbol(repository: Repository, code_map: CodeMap, name: str = "", **_) -> str:
    """Where a function or class is defined, and which files call it."""
    definitions = code_map.symbol_index.get(name, [])
    callers = [f for f, node in code_map.files.items() if name in node.calls and f not in definitions]

    if not definitions and not callers:
        return f"No symbol named {name!r} found in this project."

    report = []
    for file in definitions:
        node = code_map.files[file]
        for symbol in node.functions + node.classes:
            if symbol.name == name:
                report.append(f"defined: {file}:{symbol.line}-{symbol.end_line} ({symbol.kind})")
    report += [f"called in: {file}" for file in callers]
    return "\n".join(report)


TOOLS = {
    "list_files": list_files,
    "read_file": read_file,
    "search": search,
    "find_symbol": find_symbol,
}

DESCRIPTIONS = """\
- list_files                          every source file in the project
- read_file {path, start?, end?}      read a file, optionally a line range
- search {pattern}                    regex search across the project
- find_symbol {name}                  where a function or class is defined and called"""
