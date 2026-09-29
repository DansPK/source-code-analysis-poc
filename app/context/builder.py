"""Assemble everything the AI is shown about one finding (spec §5.6, §7).

Every excerpt is truncated to `max_snippet_lines`. That bound is the design: the model
should receive a flow, not a repository.
"""

from pathlib import Path

from app.config.settings import Settings
from app.context.call_graph import callees
from app.context.cross_file import trace_to_entry_point
from app.context.symbol_resolver import enclosing_function, excerpt, read_source
from app.models import CodeMap, Finding, FindingContext, Repository


def build_context(
    repository: Repository,
    code_map: CodeMap,
    finding: Finding,
    settings: Settings,
) -> FindingContext:
    root = Path(repository.root)
    function = enclosing_function(code_map, finding.file, finding.line)

    chain, caller_symbols = trace_to_entry_point(
        root, code_map, repository, finding.file, function, settings.max_caller_depth
    )

    callee_symbols = (
        callees(root, code_map, function, settings.max_callee_depth) if function else []
    )

    node = code_map.files.get(finding.file)
    return FindingContext(
        finding=finding,
        function_source=read_source(root, function, settings.max_snippet_lines) if function else "",
        imports=node.imports if node else [],
        callers=[excerpt(root, s, settings.max_snippet_lines) for s in caller_symbols],
        callees=[excerpt(root, s, settings.max_snippet_lines) for s in callee_symbols],
        flow_chain=chain,
    )
