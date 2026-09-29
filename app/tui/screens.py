"""Overlay screens: sessions, file list, file viewer."""

import json
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static


class _Picker(ModalScreen):
    """A filtered list. Enter picks, Escape closes."""

    BINDINGS = [Binding("escape", "dismiss", "close")]

    def __init__(self, title: str, rows: list[tuple[str, str]]):
        super().__init__()
        self.title_text, self.rows = title, rows

    def compose(self) -> ComposeResult:
        with Vertical(classes="picker"):
            yield Label(f" {self.title_text}", classes="picker-title")
            yield Input(placeholder="filter", id="filter")
            yield ListView(id="rows")

    def on_mount(self) -> None:
        self._fill(self.rows)
        self.query_one("#filter", Input).focus()

    def _fill(self, rows) -> None:
        listing = self.query_one("#rows", ListView)
        listing.clear()
        for key, label in rows[:300]:
            item = ListItem(Static(label))
            item.key = key
            listing.append(item)

    def on_input_changed(self, event: Input.Changed) -> None:
        needle = event.value.lower()
        self._fill([r for r in self.rows if needle in r[1].lower()])

    def on_input_submitted(self) -> None:
        listing = self.query_one("#rows", ListView)
        if listing.children:
            self.dismiss(listing.children[0].key)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.dismiss(event.item.key)


class SessionPicker(_Picker):
    def __init__(self, sessions: list[Path]):
        rows = []
        for path in sessions:
            try:
                entries = json.loads(path.read_text())["transcript"]
            except (OSError, ValueError, KeyError):
                continue
            first = next(
                (e[10:] for e in entries if e.startswith("QUESTION: ")), "(empty)"
            )
            rows.append((str(path), f"{path.stem}   {first[:60]}"))
        super().__init__("sessions", rows)


class FilePicker(_Picker):
    def __init__(self, files):
        super().__init__(
            "files", [(f.path, f"{f.path}   [dim]{f.language}[/]") for f in files]
        )


class FileViewer(ModalScreen):
    """Read a file, centred on a cited line."""

    BINDINGS = [Binding("escape", "dismiss", "close")]

    def __init__(self, root: str, path: str, line: int = 0):
        super().__init__()
        self.root, self.path, self.line = root, path, line

    def compose(self) -> ComposeResult:
        try:
            source = (Path(self.root) / self.path).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            yield Static(f"[red]Cannot read {self.path}: {exc}[/]")
            return

        start = max(0, self.line - 25) if self.line else 0
        shown = source[start : start + 60]
        body = [
            f"[reverse]{n:>5}  {text}[/]" if n == self.line else f"[dim]{n:>5}[/]  {text}"
            for n, text in enumerate(shown, start=start + 1)
        ]
        with Vertical(classes="picker"):
            yield Label(f" {self.path}" + (f":{self.line}" if self.line else ""),
                        classes="picker-title")
            yield Static("\n".join(body), classes="file-body")
