"""Project structure and the code map (spec §5.2, §5.3).

The code map records what each file defines, imports and calls, plus an index from
symbol name to the files defining it. That is enough for M5 to walk from a finding to
its callers and callees. Resolution is by name only -- no type inference -- so a name
can map to several files.
"""

from typing import Literal

from pydantic import BaseModel, Field


class SourceFile(BaseModel):
    path: str  # relative to the repository root
    language: str


class Repository(BaseModel):
    root: str  # absolute path on disk; every other path is relative to it
    origin: str | None = None  # Git URL, if cloned
    single_file: str | None = None  # set when the user asked to scan one file, not a tree
    files: list[SourceFile] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)


class Symbol(BaseModel):
    """A function or class definition and the lines it spans."""

    name: str
    kind: Literal["function", "class"]
    file: str
    line: int
    end_line: int


class FileNode(BaseModel):
    file: str
    imports: list[str] = Field(default_factory=list)
    functions: list[Symbol] = Field(default_factory=list)
    classes: list[Symbol] = Field(default_factory=list)
    calls: list[str] = Field(default_factory=list)


class CodeMap(BaseModel):
    files: dict[str, FileNode] = Field(default_factory=dict)
    symbol_index: dict[str, list[str]] = Field(default_factory=dict)  # name -> defining files
