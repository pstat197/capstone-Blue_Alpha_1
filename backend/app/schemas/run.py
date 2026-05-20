from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

RunLifecycleStatus = Literal["queued", "running", "completed", "failed", "cancelled", "already_completed"]
RunMode = Literal["mock", "real_tiny", "real_full"]


class RunProgress(BaseModel):
    total_runs: int = 0
    completed_runs: int = 0
    failed_runs: int = 0
    active_target_channel: str | None = None
    active_mu: float | None = None
    active_sigma: float | None = None
    active_dist: str | None = None


class ChannelRunProgress(BaseModel):
    channel: str
    total_runs: int
    completedRuns: int = 0
    failedRuns: int = 0
    status: RunLifecycleStatus = "queued"


class RunCreateRequest(BaseModel):
    workflow_id: str
    approved_config_preview: dict[str, Any] = Field(default_factory=dict)
    mode: RunMode = "mock"


class RunStatus(BaseModel):
    run_id: str
    workflow_id: str
    status: RunLifecycleStatus
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    progress: RunProgress
    channel_progress: list[ChannelRunProgress]
    messages: list[str] = Field(default_factory=list)
    monitor_url: str
    result_url: str | None = None
    mode: RunMode = "mock"
    work_dir: str | None = None
    config_path: str | None = None
    log_path: str | None = None
    process_id: int | None = None
    output_tag: str | None = None
    result_artifacts: dict[str, Any] = Field(default_factory=dict)
    display_result_id: str | None = None
    config_fingerprint: str | None = None
    original_csv_filename: str | None = None
    csv_name_prefix: str | None = None
    dataset_hash: str | None = None
    history_id: str | None = None


class RunCreateResponse(RunStatus):
    pass


class RunLogsResponse(BaseModel):
    run_id: str
    lines: list[str] = Field(default_factory=list)
