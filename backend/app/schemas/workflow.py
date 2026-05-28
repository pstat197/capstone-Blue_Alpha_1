from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkflowDraft(BaseModel):
    workflow_id: str
    upload_id: str | None = None
    name: str = "Untitled prior-sensitivity analysis"
    dataset: dict[str, Any] = Field(default_factory=dict)
    column_mapping: dict[str, Any] = Field(default_factory=dict)
    outcome: dict[str, Any] = Field(default_factory=dict)
    prior_grid: dict[str, Any] = Field(default_factory=dict)
    structural: dict[str, Any] = Field(default_factory=dict)
    sampler: dict[str, Any] = Field(default_factory=dict)
    status: str = "draft"


class WorkflowCreateRequest(BaseModel):
    upload_id: str | None = None
    name: str | None = None
    dataset: dict[str, Any] | None = None
    column_mapping: dict[str, Any] | None = None
    outcome: dict[str, Any] | None = None
    prior_grid: dict[str, Any] | None = None
    structural: dict[str, Any] | None = None
    sampler: dict[str, Any] | None = None


class WorkflowPatchRequest(BaseModel):
    name: str | None = None
    dataset: dict[str, Any] | None = None
    column_mapping: dict[str, Any] | None = None
    outcome: dict[str, Any] | None = None
    prior_grid: dict[str, Any] | None = None
    structural: dict[str, Any] | None = None
    sampler: dict[str, Any] | None = None


class ConfigPreview(BaseModel):
    workflow_id: str
    yaml: str
    estimated_run_count: int
    warnings: list[str]
    errors: list[str]
    normalized_config: dict[str, Any]
