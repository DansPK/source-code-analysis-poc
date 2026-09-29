"""The normalized finding produced by a static scanner (spec §5.5).

`findings/parser.py` translates Semgrep's JSON into this; nothing after that parser
knows Semgrep exists.
"""

from pydantic import BaseModel


class Finding(BaseModel):
    """One *candidate* vulnerability. The AI stage decides whether it is real."""

    id: str
    file: str  # relative to the repository root
    line: int
    rule_id: str
    vulnerability_type: str  # e.g. "SQL Injection"
    scanner_severity: str  # raw string from the scanner
    message: str
    code_snippet: str = ""
