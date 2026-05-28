from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.workflow import ConfigPreview, WorkflowCreateRequest, WorkflowDraft, WorkflowPatchRequest
from backend.app.services.config_builder import build_config_preview
from backend.app.services.workflow_store import create_workflow, get_workflow, patch_workflow

router = APIRouter(tags=["workflows"])


@router.post("/workflows", response_model=WorkflowDraft)
def create_workflow_draft(request: WorkflowCreateRequest) -> WorkflowDraft:
    return create_workflow(request)


@router.get("/workflows/{workflow_id}", response_model=WorkflowDraft)
def read_workflow_draft(workflow_id: str) -> WorkflowDraft:
    try:
        return get_workflow(workflow_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/workflows/{workflow_id}", response_model=WorkflowDraft)
def update_workflow_draft(workflow_id: str, request: WorkflowPatchRequest) -> WorkflowDraft:
    try:
        return patch_workflow(workflow_id, request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/workflows/{workflow_id}/config/preview", response_model=ConfigPreview)
def preview_workflow_config(workflow_id: str) -> ConfigPreview:
    try:
        draft = get_workflow(workflow_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return build_config_preview(draft)
