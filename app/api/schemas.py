"""Request shape for the API.

The response is a `ScanReport` -- already a Pydantic model, so FastAPI serializes it
and documents it without a second set of types.
"""

from pydantic import BaseModel, Field, model_validator


class ScanRequest(BaseModel):
    repo_url: str | None = Field(default=None, description="Git repository URL to clone")
    path: str | None = Field(default=None, description="Local directory or file on the server")
    mock: bool | None = Field(
        default=None, description="Use canned LLM responses; omit to follow the server config"
    )

    @model_validator(mode="after")
    def exactly_one_source(self):
        if bool(self.repo_url) == bool(self.path):
            raise ValueError("Provide exactly one of 'repo_url' or 'path'.")
        return self
