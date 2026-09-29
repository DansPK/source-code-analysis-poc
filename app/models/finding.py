"""The normalized finding produced by a static scanner.

`Finding` is the scanner-independent currency of the pipeline (spec §5.5). Semgrep's
JSON is translated into it by `app/findings/parser.py`, and nothing downstream of that
parser knows Semgrep exists. Adding another scanner means writing another parser that
produces these, and changing nothing else.
"""

from pydantic import BaseModel, Field


class Finding(BaseModel):
    """One candidate vulnerability. *Candidate* -- not a confirmed one.

    The AI stage decides whether it is real; until then every finding is a suspicion.
    """

    id: str = Field(description="Stable id within one scan, e.g. 'F-001'")

    # Location. `file` is always relative to the repository root so that findings,
    # code map entries and report output all speak the same paths.
    file: str = Field(description="Path relative to the repository root")
    line: int = Field(ge=1)
    end_line: int | None = Field(default=None, ge=1)

    # What the scanner matched.
    rule_id: str = Field(description="Scanner rule identifier, e.g. 'python-sqli-concat'")
    vulnerability_type: str = Field(description="Human label, e.g. 'SQL Injection'")
    scanner_severity: str = Field(description="Raw severity string as the scanner reported it")
    message: str = Field(description="The scanner's own explanation of the match")
    code_snippet: str = Field(default="", description="Source at the match, read from disk")

    # Which scanner produced this, so a multi-scanner run stays attributable.
    scanner: str = "semgrep"

    @property
    def location(self) -> str:
        """`path/to/file.py:42`, the form used in reports and log lines."""
        return f"{self.file}:{self.line}"
