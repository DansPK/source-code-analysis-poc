"""Map a finding's line number back to the code around it."""

from pathlib import Path

from app.models import CodeExcerpt, CodeMap, Symbol


def enclosing_function(code_map: CodeMap, file: str, line: int) -> Symbol | None:
    """The innermost function containing `line`, or None if it is module-level."""
    node = code_map.files.get(file)
    if not node:
        return None
    containing = [f for f in node.functions if f.line <= line <= f.end_line]
    if not containing:
        return None
    return min(containing, key=lambda s: s.end_line - s.line)


def read_source(root: Path, symbol: Symbol, max_lines: int) -> str:
    """The symbol's source, truncated to `max_lines`."""
    try:
        lines = (root / symbol.file).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return ""

    body = lines[symbol.line - 1 : symbol.end_line]
    if len(body) > max_lines:
        body = body[:max_lines] + [f"    # ... {len(body) - max_lines} more lines"]
    return "\n".join(body)


def excerpt(root: Path, symbol: Symbol, max_lines: int, ) -> CodeExcerpt:
    return CodeExcerpt(
        file=symbol.file,
        start_line=symbol.line,
        end_line=symbol.end_line,
        content=read_source(root, symbol, max_lines),
    )
