"""Who calls what.

The code map records calls per *file*, not per function, so narrowing a call to the
function that makes it is done by looking for the name in that function's source. That
is approximate -- a name inside a comment or string counts -- but it is cheap, needs no
second parse, and a wrong caller costs the AI a little context rather than a wrong
verdict.
"""

import re
from pathlib import Path

from app.models import CodeMap, Symbol
from app.context.symbol_resolver import read_source

# Enough source to find a call in; not a display limit.
_SEARCH_LINES = 2000


def _calls_name(source: str, name: str) -> bool:
    return re.search(rf"\b{re.escape(name)}\s*\(", source) is not None


def calling_functions(root: Path, code_map: CodeMap, file: str, name: str) -> list[Symbol]:
    """Functions in `file` whose body calls `name`."""
    node = code_map.files.get(file)
    if not node:
        return []
    return [
        function
        for function in node.functions
        if _calls_name(read_source(root, function, _SEARCH_LINES), name)
    ]


def caller_files(code_map: CodeMap, name: str) -> list[str]:
    """Files that call `name` without defining it."""
    definers = set(code_map.symbol_index.get(name, []))
    return sorted(
        file
        for file, node in code_map.files.items()
        if name in node.calls and file not in definers
    )


def callees(root: Path, code_map: CodeMap, symbol: Symbol, depth: int) -> list[Symbol]:
    """Project-defined functions reachable from `symbol`, up to `depth` levels down.

    Only symbols defined in this project are followed; library calls are left to the
    model's own knowledge.
    """
    found: dict[str, Symbol] = {}
    frontier = [symbol]

    for _ in range(depth):
        next_frontier = []
        for current in frontier:
            source = read_source(root, current, _SEARCH_LINES)
            for name, files in code_map.symbol_index.items():
                key = f"{files[0]}:{name}"
                if name == current.name or key in found or not _calls_name(source, name):
                    continue
                node = code_map.files.get(files[0])
                target = next((f for f in (node.functions if node else []) if f.name == name), None)
                if target:
                    found[key] = target
                    next_frontier.append(target)
        frontier = next_frontier
        if not frontier:
            break

    return list(found.values())
