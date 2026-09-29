"""Conversation widgets."""

import re
from pathlib import Path

from rich.markdown import Markdown
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Collapsible, Static

# "DataSeeder.java:223", "routes/search.py:17" -- a path with a line number.
CITATION = re.compile(r"\b([\w./\\-]+\.[A-Za-z]{1,10}):(\d+)\b")


class UserMessage(Static):
    def __init__(self, text: str):
        super().__init__(f"[b]you[/]\n{text}", classes="user")


class AssistantMessage(Static):
    """The model's answer. Text is appended as it streams in."""

    def __init__(self):
        super().__init__(classes="assistant")
        self.text = ""

    def append(self, chunk: str) -> None:
        self.text += chunk
        self.update(Markdown(self.text))

    def citations(self) -> list[tuple[str, int]]:
        """File references in the answer, for the citation bar."""
        seen = {}
        for path, line in CITATION.findall(self.text):
            seen.setdefault((path, int(line)), None)
        return list(seen)


class ToolCall(Static):
    """One tool invocation, shown as it runs and then with its result."""

    def __init__(self, tool: str, args: dict, why: str):
        detail = ", ".join(f"{k}={v}" for k, v in args.items())
        super().__init__(f"[dim]▸[/] [cyan]{tool}[/][dim]({detail})[/]"
                         + (f"  [dim]{why}[/]" if why else ""), classes="tool")


class Finding(Vertical):
    """One scan finding, collapsed to its headline."""

    def __init__(self, item):
        super().__init__(classes="finding")
        self.item = item

    def compose(self) -> ComposeResult:
        analysis, finding = self.item.analysis, self.item.finding
        colour = {"Critical": "red", "High": "red", "Medium": "yellow"}.get(
            analysis.severity, "green"
        )
        title = (
            f"{self.item.id}  {analysis.vulnerability_type}  "
            f"[{colour}]{analysis.severity}[/]  [dim]{analysis.confidence} confidence[/]"
        )
        with Collapsible(title=title, collapsed=True):
            body = [f"[b]{analysis.status}[/]", f"{finding.file}:{finding.line}", ""]
            if analysis.data_flow:
                body += ["[b]Data flow[/]", "  " + "\n  → ".join(analysis.data_flow), ""]
            if self.item.explanation:
                body += [self.item.explanation, ""]
            if self.item.suggested_fix:
                body += ["[b]Suggested fix[/]", self.item.suggested_fix]
            yield Static("\n".join(body))


class Citations(Static):
    """Clickable file references under an answer."""

    def __init__(self, references: list[tuple[str, int]]):
        links = "  ".join(
            f"[@click=app.open_file('{path}', {line})]{Path(path).name}:{line}[/]"
            for path, line in references[:6]
        )
        super().__init__(f"[dim]cited:[/] {links}", classes="citations")


class Notice(Static):
    def __init__(self, text: str, level: str = "info"):
        colour = {"error": "red", "ok": "green"}.get(level, "dim")
        super().__init__(f"[{colour}]{text}[/]", classes="notice")
        self.text = text
