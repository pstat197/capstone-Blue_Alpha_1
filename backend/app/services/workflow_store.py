from __future__ import annotations

import json
from uuid import uuid4

from backend.app.schemas.workflow import WorkflowCreateRequest, WorkflowDraft, WorkflowPatchRequest
from backend.app.services.paths import WORKFLOWS_DIR, ensure_storage_dirs


def _workflow_path(workflow_id: str):
    ensure_storage_dirs()
    return WORKFLOWS_DIR / f"{workflow_id}.json"


def _write_workflow(draft: WorkflowDraft) -> WorkflowDraft:
    path = _workflow_path(draft.workflow_id)
    if hasattr(draft, "model_dump_json"):
        raw = draft.model_dump_json(indent=2)
    else:
        raw = draft.json(indent=2)
    path.write_text(raw, encoding="utf-8")
    return draft


def create_workflow(request: WorkflowCreateRequest) -> WorkflowDraft:
    workflow_id = f"wf_{uuid4().hex[:12]}"
    draft = WorkflowDraft(
        workflow_id=workflow_id,
        upload_id=request.upload_id,
        name=request.name or "Untitled prior-sensitivity analysis",
        dataset=request.dataset or {},
        column_mapping=request.column_mapping or {},
        outcome=request.outcome or {},
        prior_grid=request.prior_grid or {},
        structural=request.structural or {},
        sampler=request.sampler or {},
    )
    return _write_workflow(draft)


def get_workflow(workflow_id: str) -> WorkflowDraft:
    path = _workflow_path(workflow_id)
    if not path.exists():
        raise FileNotFoundError(f"Workflow not found: {workflow_id}")
    return WorkflowDraft(**json.loads(path.read_text(encoding="utf-8")))


def patch_workflow(workflow_id: str, request: WorkflowPatchRequest) -> WorkflowDraft:
    draft = get_workflow(workflow_id)
    if hasattr(request, "model_dump"):
        updates = request.model_dump(exclude_unset=True)
    else:
        updates = request.dict(exclude_unset=True)
    for key, value in updates.items():
        if value is not None:
            setattr(draft, key, value)
    return _write_workflow(draft)
