from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ColumnProfile(BaseModel):
    name: str
    inferred_type: Literal["date", "number", "string", "boolean", "unknown"]
    null_rate: float
    nonzero_rate: float | None = None
    total_value: float | None = None
    status: Literal["valid", "warning", "missing"] = "valid"
    sample_values: list[Any]


class DetectedColumns(BaseModel):
    time_candidates: list[str]
    kpi_candidates: list[str]
    media_activity_candidates: list[dict[str, str]]
    spend_channel_candidates: list[dict[str, str]]
    revenue_candidates: list[str]
    revenue_per_kpi_candidates: list[str] = []
    control_candidates: list[str]
    geo_candidates: list[str]
    population_candidates: list[str]


class DateProfile(BaseModel):
    column: str | None = None
    date_min: str | None = None
    date_max: str | None = None
    valid_parse_rate: float = 0
    inferred_frequency: str | None = None
    status: Literal["valid", "warning", "missing"] = "missing"
    message: str


class ChannelDiagnostic(BaseModel):
    channel: str
    spend_column: str | None = None
    media_column: str | None = None
    spend_null_rate: float | None = None
    spend_nonzero_rate: float | None = None
    spend_total: float | None = None
    media_null_rate: float | None = None
    media_nonzero_rate: float | None = None
    media_total: float | None = None
    status: Literal["active_paid_media", "spend_as_media_fallback", "inactive_all_zero", "not_eligible_paid_media"]
    severity: Literal["valid", "warning", "missing"]
    include_in_model: bool
    message: str


class CsvProfile(BaseModel):
    upload_id: str
    filename: str
    storage_path: str
    row_count: int
    columns: list[ColumnProfile]
    detected: DetectedColumns
    date_profile: DateProfile
    channel_diagnostics: list[ChannelDiagnostic]
    validation_badges: list[dict[str, str]]


class CsvPreview(BaseModel):
    upload_id: str
    filename: str
    columns: list[str]
    rows: list[dict[str, Any]]
    limit: int


class UploadResponse(BaseModel):
    upload_id: str
    filename: str
    profile_url: str
