from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.run import RunCreateRequest, RunCreateResponse, RunLogsResponse, RunStatus
from backend.app.services.pipeline_launcher import read_run_logs
from backend.app.services.run_store import advance_mock_run, create_run, demo_run_status, get_run

router = APIRouter(tags=["runs"])


@router.post("/runs", response_model=RunCreateResponse)
def create_mock_run(request: RunCreateRequest) -> RunCreateResponse:
    try:
        return create_run(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}", response_model=RunStatus)
def get_run_status(run_id: str) -> RunStatus:
    if run_id == "demo_32run":
        return demo_run_status()
    try:
        return get_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/logs", response_model=RunLogsResponse)
def get_run_logs(run_id: str) -> RunLogsResponse:
    if run_id == "demo_32run":
        return RunLogsResponse(run_id=run_id, lines=demo_run_status().messages)
    try:
        return RunLogsResponse(run_id=run_id, lines=read_run_logs(run_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/mock/advance", response_model=RunStatus)
def advance_run_mock_progress(run_id: str) -> RunStatus:
    if run_id == "demo_32run":
        return demo_run_status()
    try:
        return advance_mock_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
