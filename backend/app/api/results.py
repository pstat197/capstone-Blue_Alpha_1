from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.result import ResultPayloadResponse
from backend.app.services.result_locator import load_payload_for_run
from backend.app.services.run_store import get_run

router = APIRouter(tags=["results"])


@router.get("/runs/{run_id}/results/payload", response_model=ResultPayloadResponse)
def get_result_payload(run_id: str) -> ResultPayloadResponse:
    try:
        output_tag = None
        if run_id != "demo_32run":
            output_tag = get_run(run_id).output_tag
        payload = load_payload_for_run(run_id, output_tag)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ResultPayloadResponse(run_id=run_id, payload=payload)
