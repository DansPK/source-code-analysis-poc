"""Frozen data contracts shared by every pipeline stage.

Import from `app.models` rather than the submodules -- this is the surface that is
frozen. Changing a field here means updating every consumer; see HANDOFF.md.
"""

from app.models.analysis import (
    CONFIDENCE_ORDER,
    FALLBACK_STATUS,
    SEVERITY_ORDER,
    AIAnalysis,
    CodeExcerpt,
    Confidence,
    FindingContext,
    ReportItem,
    ScanReport,
    Severity,
    Status,
)
from app.models.finding import Finding
from app.models.repository import CodeMap, FileNode, Repository, SourceFile, Symbol, SymbolKind

__all__ = [
    # finding
    "Finding",
    # repository / code map
    "SourceFile",
    "Repository",
    "Symbol",
    "SymbolKind",
    "FileNode",
    "CodeMap",
    # context / analysis / report
    "CodeExcerpt",
    "FindingContext",
    "AIAnalysis",
    "ReportItem",
    "ScanReport",
    # enums and orderings
    "Status",
    "Severity",
    "Confidence",
    "SEVERITY_ORDER",
    "CONFIDENCE_ORDER",
    "FALLBACK_STATUS",
]
