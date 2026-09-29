"""Machine-readable report."""

from datetime import datetime
from pathlib import Path

from app.models import ScanReport


def write(report: ScanReport, out_dir: str) -> Path:
    """Write the report and return the file path."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"scan-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path
