"""The FastAPI application, and the `scan-api` entry point."""

from fastapi import FastAPI

from app.api.routes import router
from app.config.settings import get_settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Source Code Vulnerability Scanner",
        description=(
            "Semgrep finds suspicious code, cross-file context is gathered around each "
            "finding, an LLM judges whether it is real, and an agent explains it."
        ),
        version="0.1.0",
    )
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
