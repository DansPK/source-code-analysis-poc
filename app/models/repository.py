"""Project structure and the whole-project code map (spec §5.2, §5.3).

The code map is deliberately lightweight: it records what each file defines, imports and
calls, and an index from symbol name to the files defining it. That is enough to walk from
a finding outward to its callers and callees, which is all the cross-file investigation
needs. It is not a compiler-grade call graph, and it resolves by *name* only -- no type
inference, no scope analysis. Ambiguity is expected and is why `defining_files()` returns
a list.
"""

from typing import Literal

from pydantic import BaseModel, Field

SymbolKind = Literal["function", "class"]


class SourceFile(BaseModel):
    path: str = Field(description="Path relative to the repository root")
    language: str = Field(description="Detected language, e.g. 'python'; 'unknown' if unclear")
    loc: int = Field(default=0, ge=0, description="Line count")


class Repository(BaseModel):
    """The analyzed project, however it was obtained (Git clone or local path)."""

    root: str = Field(description="Absolute path to the project root on disk")
    origin: str | None = Field(default=None, description="Git URL, if it came from one")
    files: list[SourceFile] = Field(default_factory=list)

    # Populated by the repository analyzer.
    languages: dict[str, int] = Field(
        default_factory=dict, description="Language -> file count, most used first when read"
    )
    frameworks: list[str] = Field(default_factory=list, description="e.g. ['flask']")
    entry_points: list[str] = Field(
        default_factory=list, description="Files that accept external input (routes, main)"
    )
    dependency_files: list[str] = Field(default_factory=list, description="requirements.txt etc.")

    @property
    def primary_language(self) -> str:
        if not self.languages:
            return "unknown"
        return max(self.languages.items(), key=lambda kv: kv[1])[0]


class Symbol(BaseModel):
    """A function or class definition, with the line range it spans."""

    name: str
    kind: SymbolKind
    file: str = Field(description="Path relative to the repository root")
    line: int = Field(ge=1, description="First line of the definition")
    end_line: int = Field(ge=1, description="Last line of the definition")

    def contains_line(self, line: int) -> bool:
        return self.line <= line <= self.end_line


class FileNode(BaseModel):
    """What one source file defines, imports and calls."""

    file: str
    imports: list[str] = Field(
        default_factory=list, description="Imported module or symbol names, as written"
    )
    functions: list[Symbol] = Field(default_factory=list)
    classes: list[Symbol] = Field(default_factory=list)
    calls: list[str] = Field(
        default_factory=list, description="Names of functions called anywhere in the file"
    )

    def enclosing_function(self, line: int) -> Symbol | None:
        """The innermost function containing `line`, or None if the line is top-level."""
        candidates = [f for f in self.functions if f.contains_line(line)]
        if not candidates:
            return None
        return min(candidates, key=lambda s: s.end_line - s.line)


class CodeMap(BaseModel):
    """Whole-project relationships, keyed by repository-relative path."""

    files: dict[str, FileNode] = Field(default_factory=dict)
    symbol_index: dict[str, list[str]] = Field(
        default_factory=dict, description="Symbol name -> files defining it (may be several)"
    )

    def defining_files(self, symbol: str) -> list[str]:
        """Files defining `symbol`. Empty when it is external or unresolvable."""
        return self.symbol_index.get(symbol, [])

    def callers_of(self, symbol: str) -> list[str]:
        """Files that call `symbol`, excluding the files that define it."""
        definers = set(self.defining_files(symbol))
        return [f for f, node in self.files.items() if symbol in node.calls and f not in definers]
