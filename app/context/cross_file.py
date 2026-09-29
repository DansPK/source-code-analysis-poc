"""Walk from a finding back to where the data came from (spec §6).

A scanner reports the line where something dangerous happens. The value that makes it
dangerous usually arrives from another file, so this walks *up* the call chain from the
sink towards an entry point and returns the path in source-to-sink order.
"""

from pathlib import Path

from app.models import CodeMap, Repository, Symbol
from app.context.call_graph import caller_files, calling_functions


def trace_to_entry_point(
    root: Path,
    code_map: CodeMap,
    repository: Repository,
    sink_file: str,
    sink_function: Symbol | None,
    max_depth: int,
) -> tuple[list[str], list[Symbol]]:
    """Return (flow chain of files, the caller functions found along it).

    The chain is ordered source -> sink, so it reads the way the data travels. It stops
    at an entry point, when nothing calls the current function, or at `max_depth` --
    whichever comes first.
    """
    chain = [sink_file]
    callers: list[Symbol] = []

    if sink_function is None or sink_file in repository.entry_points:
        return chain, callers

    current = sink_function.name
    for _ in range(max_depth):
        files = caller_files(code_map, current)
        if not files:
            break

        # Several files may call the same name; prefer one that is an entry point, so
        # the chain reaches the place external input actually arrives.
        caller_file = next((f for f in files if f in repository.entry_points), files[0])
        functions = calling_functions(root, code_map, caller_file, current)
        if not functions:
            break

        chain.append(caller_file)
        callers.append(functions[0])
        current = functions[0].name

        if caller_file in repository.entry_points:
            break

    chain.reverse()
    return chain, callers
