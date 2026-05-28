from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.result import ResultHistoryDeleteResponse, ResultHistoryPayloadResponse, ResultHistoryResponse, ResultPayloadResponse
from backend.app.services.result_locator import delete_saved_history_result, list_saved_result_history, load_payload_for_run, load_saved_history_payload
from backend.app.services.run_store import get_run

router = APIRouter(tags=["results"])


@router.get("/results/history", response_model=ResultHistoryResponse)
def get_result_history() -> ResultHistoryResponse:
    return ResultHistoryResponse(items=list_saved_result_history())


@router.get("/results/history/{history_id}", response_model=ResultHistoryPayloadResponse)
def get_result_history_payload(history_id: str) -> ResultHistoryPayloadResponse:
    try:
        item, payload = load_saved_history_payload(history_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ResultHistoryPayloadResponse(
        history_id=history_id,
        history_item=item,
        run_id=item["run_id"],
        output_tag=item["output_tag"],
        source="Saved local result",
        payload=payload,
    )


@router.delete("/results/history/{history_id}", response_model=ResultHistoryDeleteResponse)
def delete_result_history_item(history_id: str) -> ResultHistoryDeleteResponse:
    try:
        result = delete_saved_history_result(history_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Could not delete this result. Please try again.") from exc
    return ResultHistoryDeleteResponse(**result)


@router.get("/runs/{run_id}/results/payload", response_model=ResultPayloadResponse)
def get_result_payload(run_id: str) -> ResultPayloadResponse:
    try:
        run = get_run(run_id)
        output_tag = run.output_tag
        payload = load_payload_for_run(run_id, output_tag)
    except FileNotFoundError as exc:
        try:
            output_tag = run_id
            payload = load_payload_for_run(run_id, output_tag)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return ResultPayloadResponse(run_id=run_id, output_tag=output_tag, source="Saved local result", payload=payload)
    source = "FastAPI" if run.mode in {"real_full", "real_tiny"} else "Mock execution"
    return ResultPayloadResponse(run_id=run_id, output_tag=output_tag, source=source, payload=payload)


@router.get("/runs/{run_id}/results", response_model=ResultPayloadResponse)
def get_run_results(run_id: str) -> ResultPayloadResponse:
    return get_result_payload(run_id)
