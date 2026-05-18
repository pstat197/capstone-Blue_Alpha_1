from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.result import ResultPayloadResponse
from backend.app.services.result_locator import load_payload_for_run
from backend.app.services.run_store import get_run

router = APIRouter(tags=["results"])


@router.get("/runs/{run_id}/results/payload", response_model=ResultPayloadResponse)
def get_result_payload(run_id: str) -> ResultPayloadResponse:
    try:
        run = get_run(run_id)
        output_tag = run.output_tag
        payload = load_payload_for_run(run_id, output_tag)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    source = "FastAPI" if run.mode in {"real_full", "real_tiny"} else "Mock execution"
    return ResultPayloadResponse(run_id=run_id, output_tag=output_tag, source=source, payload=payload)


@router.get("/runs/{run_id}/results", response_model=ResultPayloadResponse)
def get_run_results(run_id: str) -> ResultPayloadResponse:
    return get_result_payload(run_id)
