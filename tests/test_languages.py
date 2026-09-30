"""M10: the code map and cross-file context beyond Python.

Each fixture repeats the Flask one in another stack -- route, service, repository, with
string-built SQL at the bottom -- so the same walk must come out the same way.
"""

from pathlib import Path

import pytest

from app.config.settings import Settings
from app.context.builder import build_context
from app.findings.parser import parse_semgrep
from app.repository.analyzer import analyze
from app.scanners.semgrep_scanner import scan
from app.source.loader import load_source

RULES = str(Settings.model_fields["semgrep_configs"].default).split(",")[-1]
JAVA = "src/main/java/com/example/demo"

CASES = {
    "spring_app": {
        "language": "java",
        "framework": "spring",
        "rule": "java-sqli-concat",
        "chain": [
            f"{JAVA}/controller/UserController.java",
            f"{JAVA}/service/UserService.java",
            f"{JAVA}/repository/UserRepository.java",
        ],
        "sink_function": "findByName",
    },
    "express_app": {
        "language": "javascript",
        "framework": "express",
        "rule": "javascript-sqli-concat",
        "chain": ["routes/search.js", "services/searchService.js", "db/userRepository.js"],
        "sink_function": "findUsersByName",
    },
}


@pytest.fixture(scope="module", params=sorted(CASES))
def case(request):
    root = Path("tests/vulnerable_samples", request.param).resolve()
    repository = load_source(None, str(root), Settings())
    code_map = analyze(repository)
    findings = parse_semgrep(scan(root, RULES), root)
    return CASES[request.param], repository, code_map, findings


def test_language_and_framework_are_detected(case):
    expected, repository, _, _ = case
    assert expected["language"] in repository.languages
    assert expected["framework"] in repository.frameworks


def test_only_the_request_layer_is_an_entry_point(case):
    """A repository importing its framework's data package must not count as an entry
    point, or the walk would stop at the sink."""
    expected, repository, _, _ = case
    assert expected["chain"][0] in repository.entry_points
    assert expected["chain"][-1] not in repository.entry_points


def test_our_rule_finds_the_sink(case):
    expected, _, _, findings = case
    assert [(f.rule_id.rsplit(".", 1)[-1], f.file) for f in findings] == [
        (expected["rule"], expected["chain"][-1])
    ]


def test_context_walks_from_route_to_sink(case):
    """The same cross-file chain the Flask fixture produces, in another language."""
    expected, repository, code_map, findings = case
    context = build_context(repository, code_map, findings[0], Settings())

    assert context.flow_chain == expected["chain"]
    assert expected["sink_function"] in context.function_source
    assert [c.file for c in context.callers] == expected["chain"][-2::-1]


@pytest.mark.parametrize(
    ("filename", "source", "functions", "calls", "imports"),
    [
        ("main.go", 'package main\nimport "net/http"\nfunc handler(w http.ResponseWriter, r *http.Request) {\n\tdb.Query("x")\n}\n',
         ["handler"], ["Query"], ["net/http"]),
        ("Api.cs", "using Microsoft.AspNetCore.Mvc;\nclass Api {\n  void Get() { Db.Run(); }\n}\n",
         ["Get"], ["Run"], ["Microsoft.AspNetCore.Mvc"]),
        ("index.php", "<?php\nuse Illuminate\\Http\\Request;\nfunction show($r) { $db->query($r); }\n",
         ["show"], ["query"], ["Illuminate\\Http\\Request"]),
        ("app.rb", "require 'sinatra'\ndef lookup(id)\n  DB.execute(id)\nend\n",
         ["lookup"], ["execute"], ["sinatra"]),
        ("main.rs", "use std::process::Command;\nfn run(c: &str) { Command::new(c).spawn(); }\n",
         ["run"], ["new"], ["std::process::Command"]),
        ("main.c", "#include <stdlib.h>\nint run(char *c) { return system(c); }\n",
         ["run"], ["system"], ["stdlib.h"]),
        ("Main.kt", "import io.ktor.server.application.*\nfun serve() { respond(\"x\") }\n",
         ["serve"], ["respond"], ["io.ktor.server.application.*"]),
    ],
)
def test_other_languages_map_definitions_calls_and_imports(tmp_path, filename, source, functions, calls, imports):
    (tmp_path / filename).write_text(source)
    repository = load_source(None, str(tmp_path), Settings())

    node = analyze(repository).files[filename]

    assert [f.name for f in node.functions] == functions
    assert set(calls) <= set(node.calls)
    assert node.imports == imports


def test_using_a_c_struct_is_not_defining_one(tmp_path):
    """Otherwise every file declaring `struct stat st;` would "define" stat."""
    (tmp_path / "a.c").write_text("struct stat st;\nstruct point { int x; };\n")
    repository = load_source(None, str(tmp_path), Settings())

    assert [c.name for c in analyze(repository).files["a.c"].classes] == ["point"]
