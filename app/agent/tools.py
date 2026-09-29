"""The actions the ask agent can take on a project.

Each tool takes plain arguments and returns text. Output is truncated, because
everything returned here goes back into the next prompt.
"""

import re
from pathlib import Path

from app.config.settings import Settings
from app.findings.deduplicator import deduplicate
from app.findings.parser import parse_semgrep
from app.models import CodeMap, Repository
from app.scanners import ScannerError
from app.scanners.semgrep_scanner import scan as run_semgrep

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


def run_scanner(
    repository: Repository, settings: Settings, path: str = "", **_
) -> str:
    """Run Semgrep over the project, or one subdirectory of it.

    This is deterministic detection, not a second opinion from a model: it reports
    what the rules match, which is a different kind of evidence from reading code.
    """
    root = Path(repository.root)
    target = root / path if path else root
    if not target.exists():
        return f"No such path in this project: {path}"

    try:
        findings = deduplicate(parse_semgrep(run_semgrep(target, settings.semgrep_configs), root))
    except ScannerError as exc:
        return f"The scanner could not run: {exc}"

    if not findings:
        return (
            f"Semgrep reported nothing in {path or 'the project'}. Its rules cover common "
            "patterns only, so this is not proof the code is safe."
        )

    lines = [f"{len(findings)} finding(s):"]
    lines += [
        f"{f.file}:{f.line}  {f.vulnerability_type}  [{f.rule_id.rsplit('.', 1)[-1]}]\n"
        f"    {f.message.strip()[:200]}"
        for f in findings[:30]
    ]
    if len(findings) > 30:
        lines.append(f"... {len(findings) - 30} more")
    return "\n".join(lines)


TOOLS = {
    "list_files": list_files,
    "read_file": read_file,
    "search": search,
    "find_symbol": find_symbol,
    "run_scanner": run_scanner,
}

DESCRIPTIONS = """\
- list_files                          every source file in the project
- read_file {path, start?, end?}      read a file, optionally a line range
- search {pattern}                    regex search across the project
- find_symbol {name}                  where a function or class is defined and called
- run_scanner {path?}                 run Semgrep static analysis over the project, or one
                                      subdirectory. Use it when the question is about
                                      vulnerabilities, security or code quality, and you want
                                      rule-based evidence rather than your own reading. It is
                                      the slowest tool, taking up to a minute on a large
                                      project, so call it once and narrow with `path` if you
                                      only care about part of the tree. Its silence is not
                                      proof of safety: the rules cover common patterns only,
                                      so confirm anything important by reading the code."""
