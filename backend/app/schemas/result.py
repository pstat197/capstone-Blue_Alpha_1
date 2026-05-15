from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ResultPayloadResponse(BaseModel):
    run_id: str
    payload: dict[str, Any]
