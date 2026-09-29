"""Build the whole-project code map from Python source (spec §5.3).

One `ast` pass per file collects what it imports, what it defines, and what it calls.
Symbols are matched by name only -- no scope or type analysis -- which is enough to
connect `routes/search.py` to `database/user_repository.py` and cheap enough to run on
a whole project.
"""

import ast
from pathlib import Path

from app.models import CodeMap, FileNode, Symbol
from app.utils.logging import get_logger

logger = get_logger(__name__)


class _Collector(ast.NodeVisitor):
    def __init__(self, relative_path: str):
        self.node = FileNode(file=relative_path)

    def visit_Import(self, node: ast.Import) -> None:
        self.node.imports.extend(alias.name for alias in node.names)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # `from services.search_service import search_users` records the module, so
        # framework detection sees "flask", and the symbol, so calls can be resolved.
        if node.module:
            self.node.imports.append(node.module)
        self.node.imports.extend(alias.name for alias in node.names)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add_symbol(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._add_symbol(node, "function")

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add_symbol(node, "class")

    def visit_Call(self, node: ast.Call) -> None:
        name = _called_name(node.func)
        if name:
            self.node.calls.append(name)
        self.generic_visit(node)

    def _add_symbol(self, node, kind: str) -> None:
        symbol = Symbol(
            name=node.name,
            kind=kind,
            file=self.node.file,
            line=node.lineno,
            end_line=node.end_lineno or node.lineno,
        )
        (self.node.functions if kind == "function" else self.node.classes).append(symbol)
        self.generic_visit(node)  # keep descending: nested defs count too


def _called_name(func: ast.expr) -> str | None:
    """`search_users(...)` -> 'search_users'; `cursor.execute(...)` -> 'execute'."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def build_code_map(root: Path, python_files: list[str]) -> CodeMap:
    """Parse each file (paths relative to `root`) into the map."""
    code_map = CodeMap()
    for relative_path in python_files:
        try:
            source = (root / relative_path).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            logger.warning("Skipping %s: %s", relative_path, exc)
            continue

        collector = _Collector(relative_path)
        collector.visit(tree)
        code_map.files[relative_path] = collector.node

        for symbol in collector.node.functions + collector.node.classes:
            code_map.symbol_index.setdefault(symbol.name, []).append(relative_path)

    return code_map
