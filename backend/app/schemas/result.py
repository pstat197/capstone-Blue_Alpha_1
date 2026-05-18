from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ResultPayloadResponse(BaseModel):
    run_id: str
    output_tag: str | None = None
    source: str = "run_artifact"
    payload: dict[str, Any]
