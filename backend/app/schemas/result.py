from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ResultPayloadResponse(BaseModel):
    run_id: str
    output_tag: str | None = None
    source: str = "run_artifact"
    payload: dict[str, Any]


class ResultHistoryItem(BaseModel):
    history_id: str
    run_id: str
    output_tag: str
    display_result_id: str | None = None
    config_fingerprint: str | None = None
    original_csv_filename: str | None = None
    csv_name_prefix: str | None = None
    dataset_hash: str | None = None
    generated_at: str | None = None
    completed_at: str | None = None
    kpi: str | None = None
    kpi_path: str | None = None
    revenue_handling: str | None = None
    channels: list[str] = Field(default_factory=list)
    channel_count: int = 0
    completed_runs: int | None = None
    qc_pass_runs: int | None = None
    qc_review_runs: int | None = None
    qc_fail_runs: int | None = None
    qc_mix: dict[str, int] = Field(default_factory=dict)
    report_path: str | None = None
    dashboard_path: str | None = None
    payload_path: str
    react_result_url: str | None = None
    static_report_path: str | None = None


class ResultHistoryResponse(BaseModel):
    items: list[ResultHistoryItem]


class ResultHistoryPayloadResponse(ResultPayloadResponse):
    history_id: str
    history_item: ResultHistoryItem
