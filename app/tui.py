"""Terminal UI for the ask agent.

Two kinds of history, both on disk:

- input history (`.ask/input_history`) gives arrow-key recall across runs
- conversations (`.ask/sessions/<name>.json`) are saved after every exchange, so a
  session can be resumed and the model keeps its earlier context

Conversations are stored per project, keyed by the project root, so asking about two
codebases does not mix them.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from app.agent.ask import ask
from app.ai.client import LLMClient
from app.models import CodeMap, Repository

HOME = Path.home() / ".ask"
COMMANDS = ["/help", "/clear", "/sessions", "/resume", "/history", "/files", "/exit"]


def _session_dir(repository: Repository) -> Path:
    """One directory per project, named after the root so projects stay separate."""
    digest = hashlib.sha256(repository.root.encode()).hexdigest()[:8]
    return HOME / "sessions" / f"{Path(repository.root).name}-{digest}"


class AskTUI:
    def __init__(self, client: LLMClient, repository: Repository, code_map: CodeMap):
        self.client, self.repository, self.code_map = client, repository, code_map
        self.console = Console()
        self.transcript: list[str] = []

        self.sessions = _session_dir(repository)
        self.sessions.mkdir(parents=True, exist_ok=True)
        self.session_file = self.sessions / f"{datetime.now():%Y%m%d-%H%M%S}.json"

        HOME.mkdir(parents=True, exist_ok=True)
        self.prompt = PromptSession(
            history=FileHistory(str(HOME / "input_history")),
            completer=WordCompleter(COMMANDS, sentence=True),
        )

    # --- persistence ------------------------------------------------------------

    def _save(self) -> None:
        self.session_file.write_text(
            json.dumps(
                {"root": self.repository.root, "transcript": self.transcript}, indent=2
            ),
            encoding="utf-8",
        )

    def _saved_sessions(self) -> list[Path]:
        return sorted(self.sessions.glob("*.json"), reverse=True)

    def _resume(self, name: str = "") -> None:
        available = self._saved_sessions()
        if not available:
            self.console.print("[yellow]No saved conversations for this project.[/]")
            return

        chosen = next((p for p in available if p.stem == name), available[0])
        self.transcript = json.loads(chosen.read_text(encoding="utf-8"))["transcript"]
        self.session_file = chosen
        questions = [line for line in self.transcript if line.startswith("QUESTION: ")]
        self.console.print(f"[green]Resumed {chosen.stem}[/] ({len(questions)} questions)")
        for question in questions[-3:]:
            self.console.print(f"  [dim]{question[10:][:70]}[/]")

    # --- rendering --------------------------------------------------------------

    def _banner(self) -> None:
        languages = ", ".join(self.repository.languages) or "unknown"
        frameworks = ", ".join(self.repository.frameworks)
        self.console.print(
            Panel(
                f"[bold]{self.repository.root}[/]\n"
                f"{len(self.repository.files)} files · {languages}"
                + (f" · {frameworks}" if frameworks else "")
                + f"\n[dim]{len(self._saved_sessions())} saved conversation(s). "
                f"/help for commands.[/]",
                title="ask",
                border_style="cyan",
            )
        )

    def _on_step(self, tool: str, args: dict, why: str) -> None:
        detail = ", ".join(f"{k}={v}" for k, v in args.items())
        self.console.print(f"  [dim cyan]→ {tool}([/][cyan]{detail}[/][dim cyan])[/]"
                           + (f" [dim]{why}[/]" if why else ""))

    def _command(self, line: str) -> bool:
        """Handle a /command. Returns False when the app should exit."""
        name, _, argument = line.partition(" ")
        if name in ("/exit", "/quit"):
            return False
        if name == "/help":
            self.console.print(
                "[bold]/clear[/]     forget this conversation\n"
                "[bold]/sessions[/]  list saved conversations\n"
                "[bold]/resume[/]    resume the latest, or /resume <name>\n"
                "[bold]/history[/]   questions asked in this conversation\n"
                "[bold]/files[/]     files in this project\n"
                "[bold]/exit[/]      quit"
            )
        elif name == "/clear":
            self.transcript = []
            self.session_file = self.sessions / f"{datetime.now():%Y%m%d-%H%M%S}.json"
            self.console.print("[green]Started a new conversation.[/]")
        elif name == "/sessions":
            for path in self._saved_sessions()[:15]:
                count = len(json.loads(path.read_text())["transcript"])
                self.console.print(f"  {path.stem}  [dim]{count} entries[/]")
        elif name == "/resume":
            self._resume(argument.strip())
        elif name == "/history":
            for line_ in self.transcript:
                if line_.startswith("QUESTION: "):
                    self.console.print(f"  [dim]{line_[10:]}[/]")
        elif name == "/files":
            for source_file in self.repository.files[:60]:
                self.console.print(f"  {source_file.path} [dim]{source_file.language}[/]")
        else:
            self.console.print(f"[red]Unknown command {name}. /help for the list.[/]")
        return True

    # --- main loop --------------------------------------------------------------

    def run(self) -> int:
        self._banner()
        while True:
            try:
                line = self.prompt.prompt("\nask> ").strip()
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[dim]bye[/]")
                return 0

            if not line:
                continue
            if line.startswith("/"):
                if not self._command(line):
                    return 0
                continue

            with self.console.status("[dim]thinking[/]", spinner="dots"):
                answer, self.transcript = ask(
                    self.client,
                    self.repository,
                    self.code_map,
                    line,
                    self.transcript,
                    on_step=self._on_step,
                )
            self.console.print()
            self.console.print(Markdown(answer))
            self._save()
