from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ColumnProfile(BaseModel):
    name: str
    inferred_type: Literal["date", "number", "string", "boolean", "unknown"]
    null_rate: float
    sample_values: list[Any]


class DetectedColumns(BaseModel):
    time_candidates: list[str]
    kpi_candidates: list[str]
    media_activity_candidates: list[dict[str, str]]
    spend_channel_candidates: list[dict[str, str]]
    revenue_candidates: list[str]
    control_candidates: list[str]
    geo_candidates: list[str]
    population_candidates: list[str]


class CsvProfile(BaseModel):
    upload_id: str
    filename: str
    storage_path: str
    row_count: int
    columns: list[ColumnProfile]
    detected: DetectedColumns
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
