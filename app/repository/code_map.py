"""Build the whole-project code map (spec §5.3) for every language in `LANGUAGES`.

One tree-sitter pass per file collects what it imports, what it defines, and what it
calls. Grammars differ only in their node type names, so each language is a row of
node types and the walk itself is shared. Symbols are matched by name only -- no scope
or type analysis -- which is enough to connect a route to the repository it reaches
and cheap enough to run on a whole project.
"""

import re
from pathlib import Path

from tree_sitter import Node
from tree_sitter_language_pack import get_parser

from app.models import CodeMap, FileNode, SourceFile, Symbol
from app.utils.logging import get_logger

logger = get_logger(__name__)

# language -> (function nodes, class nodes, call nodes, import nodes). Languages are the
# names `language_detector` assigns; the grammar has the same name except TSX.
LANGUAGES: dict[str, tuple[set[str], set[str], set[str], set[str]]] = {
    "python": (
        {"function_definition"},
        {"class_definition"},
        {"call"},
        {"import_statement", "import_from_statement"},
    ),
    "java": (
        {"method_declaration", "constructor_declaration"},
        {"class_declaration", "interface_declaration", "enum_declaration", "record_declaration"},
        {"method_invocation"},
        {"import_declaration"},
    ),
    "javascript": (
        {"function_declaration", "generator_function_declaration", "method_definition",
         "arrow_function", "function_expression", "function"},
        {"class_declaration"},
        {"call_expression"},
        {"import_statement"},
    ),
    "go": (
        {"function_declaration", "method_declaration"},
        {"type_spec"},
        {"call_expression"},
        {"import_spec"},
    ),
    "php": (
        {"function_definition", "method_declaration"},
        {"class_declaration", "interface_declaration", "trait_declaration"},
        {"function_call_expression", "member_call_expression", "scoped_call_expression"},
        {"namespace_use_declaration"},
    ),
    "csharp": (
        {"method_declaration", "constructor_declaration", "local_function_statement"},
        {"class_declaration", "interface_declaration", "struct_declaration", "record_declaration"},
        {"invocation_expression"},
        {"using_directive"},
    ),
    "ruby": (
        {"method", "singleton_method"},
        {"class", "module"},
        {"call"},
        set(),  # `require` is a call; see _collect
    ),
    "kotlin": (
        {"function_declaration"},
        {"class_declaration", "object_declaration"},
        {"call_expression"},
        {"import_header"},
    ),
    "scala": (
        {"function_definition"},
        {"class_definition", "object_definition", "trait_definition"},
        {"call_expression"},
        {"import_declaration"},
    ),
    "swift": (
        {"function_declaration"},
        {"class_declaration", "protocol_declaration"},
        {"call_expression"},
        {"import_declaration"},
    ),
    "rust": (
        {"function_item"},
        {"struct_item", "enum_item", "trait_item"},
        {"call_expression"},
        {"use_declaration"},
    ),
    "c": (
        {"function_definition"},
        {"struct_specifier"},
        {"call_expression"},
        {"preproc_include"},
    ),
    "cpp": (
        {"function_definition"},
        {"class_specifier", "struct_specifier"},
        {"call_expression"},
        {"preproc_include"},
    ),
}
LANGUAGES["typescript"] = LANGUAGES["javascript"]

_IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*")
# A dotted/qualified name: java.util.List, std::process, Illuminate\Http\Request.
_QUALIFIED = re.compile(r"[A-Za-z_][\w]*(?:(?:\.|::|\\)(?:[A-Za-z_][\w]*|\*))*")
_IMPORT_KEYWORDS = {"import", "from", "using", "use", "static", "type", "include", "global"}
_QUOTED = re.compile(r"""["'`]([^"'`]+)["'`]""")
_UNNAMED_FUNCTIONS = {"arrow_function", "function_expression", "function"}


def _text(node: Node) -> str:
    return node.text.decode("utf-8", errors="replace")


def _name(node: Node) -> str | None:
    """The name a definition declares.

    Most grammars put it in a `name` field. C and C++ nest it in declarators; unnamed JS
    functions take the name of what they are assigned to; a few grammars (Kotlin) have
    no field, so the first identifier child is used.
    """
    name = node.child_by_field_name("name")
    if name is None:
        declarator = node.child_by_field_name("declarator")
        while declarator is not None and declarator.child_by_field_name("declarator"):
            declarator = declarator.child_by_field_name("declarator")
        name = declarator
    if name is None and node.type in _UNNAMED_FUNCTIONS:
        parent = node.parent
        name = (parent.child_by_field_name("name") or parent.child_by_field_name("key")
                or parent.child_by_field_name("left"))
        if name is None:
            return "<anonymous>"  # a callback: still mapped, so a sink inside it has a function
    if name is None:
        name = next((c for c in node.named_children if "identifier" in c.type or c.type == "constant"), None)
    if name is None:
        return None
    identifiers = _IDENTIFIER.findall(_text(name))
    return identifiers[-1] if identifiers else None


def _called_name(node: Node) -> str | None:
    """`search_users(...)` -> 'search_users'; `cursor.execute(...)` -> 'execute'."""
    callee = (node.child_by_field_name("function") or node.child_by_field_name("method")
              or node.child_by_field_name("name") or (node.named_children or [None])[0])
    if callee is None:
        return None
    identifiers = _IDENTIFIER.findall(_text(callee).split("(")[0].split("<")[0])
    return identifiers[-1] if identifiers else None


def _imported_names(text: str) -> list[str]:
    """Module names from an import statement, whatever the language's syntax.

    A quoted path (JS, Go, C) is the module; otherwise it is the qualified names left
    once keywords and aliases are removed.
    """
    quoted = _QUOTED.findall(text)
    if quoted:
        return quoted
    text = re.sub(r"\bas\s+\w+", "", text)
    return [name for name in _QUALIFIED.findall(text) if name not in _IMPORT_KEYWORDS]


def _collect(root: Node, file_node: FileNode, language: str) -> None:
    functions, classes, calls, imports = LANGUAGES[language]
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in functions or node.type in classes:
            name = _name(node)
            # `struct stat st;` uses a C struct, it does not define one.
            if node.type.endswith("_specifier") and node.child_by_field_name("body") is None:
                name = None
            if name:
                kind = "function" if node.type in functions else "class"
                symbol = Symbol(
                    name=name, kind=kind, file=file_node.file,
                    line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                )
                (file_node.functions if kind == "function" else file_node.classes).append(symbol)
        elif node.type in calls:
            name = _called_name(node)
            if name:
                file_node.calls.append(name)
                # CommonJS and Ruby import with a call: require("express").
                if name == "require":
                    file_node.imports.extend(_QUOTED.findall(_text(node))[:1])
        elif node.type in imports:
            file_node.imports.extend(_imported_names(_text(node)))
        stack.extend(reversed(node.children))  # keep descending: nested defs count too


def build_code_map(root: Path, files: list[SourceFile]) -> CodeMap:
    """Parse every file in a supported language (paths relative to `root`) into the map."""
    code_map = CodeMap()
    for source_file in files:
        if source_file.language not in LANGUAGES:
            continue
        try:
            source = (root / source_file.path).read_bytes()
        except OSError as exc:
            logger.warning("Skipping %s: %s", source_file.path, exc)
            continue

        grammar = "tsx" if source_file.path.endswith(".tsx") else source_file.language
        # tree-sitter recovers from syntax errors, so a broken file still maps what it can.
        tree = get_parser(grammar).parse(source)
        node = FileNode(file=source_file.path)
        _collect(tree.root_node, node, source_file.language)
        code_map.files[source_file.path] = node

        for symbol in node.functions + node.classes:
            code_map.symbol_index.setdefault(symbol.name, []).append(source_file.path)

    return code_map
