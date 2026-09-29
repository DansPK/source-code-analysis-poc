"""HTTP endpoints.

Thin by design: these call `run_scan()` and translate errors into status codes. Any
logic beyond that belongs in the pipeline, not here.
"""

from fastapi import APIRouter, HTTPException

from app.ai import AIError
from app.api.schemas import ScanRequest
from app.config.settings import get_settings
from app.main import run_scan
from app.models import ScanReport
from app.scanners import ScannerError
from app.source import SourceError

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/scan", response_model=ScanReport)
def scan(request: ScanRequest) -> ScanReport:
    """Scan a repository or path and return the full report.

    Synchronous: a real scan runs Semgrep and one LLM call per finding, so it can take
    minutes. This is a `def` rather than `async def`, so FastAPI runs it in a threadpool
    and the server stays responsive. Background jobs with a job store are deliberately
    out of scope for the POC.
    """
    try:
        return run_scan(request.repo_url, request.path, get_settings())
    except SourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (ScannerError, AIError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
