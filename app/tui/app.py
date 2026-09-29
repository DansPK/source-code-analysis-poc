"""The ask TUI: a conversation with the codebase.

Work runs in Textual workers so the interface stays responsive while the model
thinks. Everything the app writes goes to `workspace/`, like the rest of the tool.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Input

from app.agent.ask import ask
from app.ai.client import LLMClient
from app.config.settings import WORKSPACE, Settings
from app.models import CodeMap, Repository
from app.tui.screens import FilePicker, FileViewer, SessionPicker
from app.tui.widgets import AssistantMessage, Citations, Finding, Notice, ToolCall, UserMessage

HELP = """Commands
  /scan            run the vulnerability scanner on this project
  /export          write this conversation to workspace/
  /new             start a fresh conversation
  /help            this message

Keys
  ctrl+s sessions   ctrl+f files   ctrl+n new   ctrl+c quit"""


class AskApp(App):
    CSS = """
    Screen { layout: vertical; }
    #log { height: 1fr; padding: 1 2; }
    .user { color: $accent; margin-top: 1; }
    .assistant { margin: 1 0; }
    .tool { color: $text-muted; }
    .citations { margin-bottom: 1; }
    .notice { margin: 1 0; }
    .finding { margin-bottom: 1; }
    Input { dock: bottom; border: tall $accent; }
    .picker { background: $surface; border: tall $accent; padding: 1; height: 80%; width: 90%; }
    .picker-title { text-style: bold; }
    .file-body { height: 1fr; overflow-y: scroll; }
    """

    BINDINGS = [
        Binding("ctrl+s", "sessions", "sessions"),
        Binding("ctrl+f", "files", "files"),
        Binding("ctrl+n", "new", "new"),
        Binding("ctrl+c", "quit", "quit"),
    ]

    def __init__(
        self,
        client: LLMClient,
        repository: Repository,
        code_map: CodeMap,
        settings: Settings,
    ):
        super().__init__()
        self.client, self.repository, self.code_map = client, repository, code_map
        self.settings = settings
        self.transcript: list[str] = []
        self.busy = False

        digest = hashlib.sha256(repository.root.encode()).hexdigest()[:8]
        self.sessions = WORKSPACE / "sessions" / f"{Path(repository.root).name}-{digest}"
        self.sessions.mkdir(parents=True, exist_ok=True)
        self.session_file = self.sessions / f"{datetime.now():%Y%m%d-%H%M%S}.json"

    # --- layout -----------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="log")
        yield Input(placeholder="ask anything, or /help")
        yield Footer()

    def on_mount(self) -> None:
        languages = ", ".join(self.repository.languages) or "unknown"
        self.title = "ask"
        self.sub_title = (
            f"{Path(self.repository.root).name} · {len(self.repository.files)} files · {languages}"
        )
        self._write(Notice(f"{self.repository.root}\n/help for commands."))
        self.query_one(Input).focus()

    def _write(self, widget):
        log = self.query_one("#log", VerticalScroll)
        log.mount(widget)
        log.scroll_end(animate=False)
        return widget

    # --- input ------------------------------------------------------------------

    @on(Input.Submitted)
    def submitted(self, event: Input.Submitted) -> None:
        line = event.value.strip()
        event.input.value = ""
        if not line or self.busy:
            return
        if line.startswith("/"):
            self._command(line)
            return
        self._write(UserMessage(line))
        self.busy = True
        self.think(line)

    def _command(self, line: str) -> None:
        name = line.split()[0]
        if name == "/help":
            self._write(Notice(HELP))
        elif name == "/new":
            self.action_new()
        elif name == "/scan":
            self.busy = True
            self._write(Notice("Scanning. This runs Semgrep and one analysis per finding."))
            self.run_scan()
        elif name == "/export":
            self._export()
        else:
            self._write(Notice(f"Unknown command {name}. /help for the list.", "error"))

    # --- work -------------------------------------------------------------------

    @work(thread=True)
    def think(self, question: str) -> None:
        answer_widget = None

        def on_step(tool, args, why):
            self.call_from_thread(self._write, ToolCall(tool, args, why))

        def on_token(chunk):
            nonlocal answer_widget
            if answer_widget is None:
                answer_widget = self.call_from_thread(self._write, AssistantMessage())
            self.call_from_thread(answer_widget.append, chunk)

        answer, self.transcript = ask(
            self.client, self.repository, self.code_map, question,
            self.transcript, on_step=on_step, on_token=on_token,
            max_steps=self.settings.max_ask_steps,
        )

        if answer_widget is None:  # the client did not stream
            answer_widget = self.call_from_thread(self._write, AssistantMessage())
            self.call_from_thread(answer_widget.append, answer)
        if references := answer_widget.citations():
            self.call_from_thread(self._write, Citations(references))
        self.call_from_thread(self._save)
        self.busy = False

    @work(thread=True)
    def run_scan(self) -> None:
        from app.main import run_scan as pipeline

        try:
            report = pipeline(None, self.repository.root, self.settings)
        except Exception as exc:  # any stage can fail; the UI must survive it
            self.call_from_thread(self._write, Notice(f"Scan failed: {exc}", "error"))
            self.busy = False
            return

        if not report.items:
            self.call_from_thread(
                self._write, Notice(f"No findings in {report.files_scanned} files.", "ok")
            )
        else:
            self.call_from_thread(
                self._write,
                Notice(f"{len(report.items)} finding(s) in {report.files_scanned} files.", "ok"),
            )
            for item in report.items:
                self.call_from_thread(self._write, Finding(item))
        self.busy = False

    # --- persistence ------------------------------------------------------------

    def _save(self) -> None:
        self.session_file.write_text(
            json.dumps({"root": self.repository.root, "transcript": self.transcript}, indent=2),
            encoding="utf-8",
        )

    def _export(self) -> None:
        target = WORKSPACE / f"conversation-{datetime.now():%Y%m%d-%H%M%S}.md"
        lines = [f"# Conversation about {self.repository.root}", ""]
        for entry in self.transcript:
            if entry.startswith("QUESTION: "):
                lines += [f"## {entry[10:]}", ""]
            elif entry.startswith("ANSWER: "):
                lines += [entry[8:], ""]
        target.write_text("\n".join(lines), encoding="utf-8")
        self._write(Notice(f"Written to {target}", "ok"))

    # --- actions ----------------------------------------------------------------

    def action_new(self) -> None:
        self.transcript = []
        self.session_file = self.sessions / f"{datetime.now():%Y%m%d-%H%M%S}.json"
        self.query_one("#log", VerticalScroll).remove_children()
        self._write(Notice("New conversation."))

    def action_sessions(self) -> None:
        saved = sorted(self.sessions.glob("*.json"), reverse=True)
        if not saved:
            self._write(Notice("No saved conversations for this project."))
            return
        self.push_screen(SessionPicker(saved), self._resume)

    def _resume(self, path: str | None) -> None:
        if not path:
            return
        self.transcript = json.loads(Path(path).read_text())["transcript"]
        self.session_file = Path(path)
        self.query_one("#log", VerticalScroll).remove_children()
        for entry in self.transcript:
            if entry.startswith("QUESTION: "):
                self._write(UserMessage(entry[10:]))
            elif entry.startswith("ANSWER: "):
                self._write(AssistantMessage()).append(entry[8:])
        self._write(Notice(f"Resumed {Path(path).stem}", "ok"))

    def action_files(self) -> None:
        self.push_screen(
            FilePicker(self.repository.files),
            lambda path: path and self.action_open_file(path, 0),
        )

    def action_open_file(self, path: str, line: int = 0) -> None:
        self.push_screen(FileViewer(self.repository.root, path, int(line)))
