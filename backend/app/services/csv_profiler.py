from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.schemas.upload import ColumnProfile, CsvProfile, DetectedColumns

CHANNEL_ALIASES = {
    "fb": "facebook",
    "ig": "instagram",
    "insta": "instagram",
    "google_ads": "google",
    "googleads": "google",
    "linked_in": "linkedin",
}

NON_MEDIA_CHANNEL_PREFIXES = {
    "all",
    "aggregate",
    "kpi",
    "outcome",
    "overall",
    "revenue",
    "sales",
    "subtotal",
    "sum",
    "total",
}


def _infer_type(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_numeric_dtype(series):
        return "number"
    non_null = series.dropna()
    if not non_null.empty:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            parsed = pd.to_datetime(non_null.head(50), errors="coerce")
        if parsed.notna().mean() >= 0.8:
            return "date"
    if pd.api.types.is_string_dtype(series) or series.dtype == object:
        return "string"
    return "unknown"


def _sample_values(series: pd.Series) -> list[Any]:
    values = []
    for value in series.dropna().head(5).tolist():
        if hasattr(value, "item"):
            value = value.item()
        values.append(value)
    return values


def _detect_columns(column_names: list[str]) -> DetectedColumns:
    lowered = {name: name.lower() for name in column_names}
    time_candidates = [
        name
        for name, lower in lowered.items()
        if lower in {"date", "week", "month", "time", "period", "time_period"} or lower.endswith("_date")
    ]
    revenue_candidates = [
        name
        for name, lower in lowered.items()
        if any(token in lower for token in ["revenue", "sales", "gmv", "income", "turnover"])
    ]
    spend_suffixes = ("_spend", "_cost", "_costs")
    activity_suffixes = ("_impressions", "_impression", "_clicks", "_click", "_views", "_view", "_conversions", "_conversion")
    ignored_channel_metric_columns = set()
    spend_channel_candidates = []
    for name in column_names:
        lower = lowered[name]
        if not lower.endswith(spend_suffixes):
            continue
        channel = _normalize_channel_name(_strip_suffix(lower, spend_suffixes))
        if channel:
            spend_channel_candidates.append({"column": name, "channel": channel})
        else:
            ignored_channel_metric_columns.add(name)

    media_activity_candidates = []
    for name in column_names:
        lower = lowered[name]
        if not lower.endswith(activity_suffixes):
            continue
        channel = _normalize_channel_name(_strip_suffix(lower, activity_suffixes))
        if channel:
            media_activity_candidates.append({"column": name, "channel": channel})
        else:
            ignored_channel_metric_columns.add(name)
    geo_candidates = [name for name, lower in lowered.items() if lower in {"geo", "state", "region", "dma", "market"}]
    population_candidates = [name for name, lower in lowered.items() if "population" in lower or lower == "pop"]
    excluded = set(time_candidates) | set(revenue_candidates) | set(geo_candidates) | set(population_candidates)
    excluded.update(item["column"] for item in spend_channel_candidates)
    excluded.update(item["column"] for item in media_activity_candidates)
    excluded.update(ignored_channel_metric_columns)
    kpi_candidates = [
        name
        for name, lower in lowered.items()
        if name not in excluded
        and not any(token in lower for token in ["promo", "holiday", "competitor", "control", "season"])
    ]
    control_candidates = [
        name
        for name, lower in lowered.items()
        if name not in excluded
        and any(token in lower for token in ["promo", "holiday", "competitor", "control", "season", "price"])
    ]
    direct_revenue_kpis = [
        name
        for name in revenue_candidates
        if lowered[name] in {"revenue", "sales", "gmv", "income", "turnover", "total_revenue"}
    ]
    kpi_candidates = [*direct_revenue_kpis, *[name for name in kpi_candidates if name not in direct_revenue_kpis]]

    return DetectedColumns(
        time_candidates=time_candidates,
        kpi_candidates=kpi_candidates,
        media_activity_candidates=media_activity_candidates,
        spend_channel_candidates=spend_channel_candidates,
        revenue_candidates=revenue_candidates,
        control_candidates=control_candidates,
        geo_candidates=geo_candidates,
        population_candidates=population_candidates,
    )


def _strip_suffix(value: str, suffixes: tuple[str, ...]) -> str:
    for suffix in suffixes:
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def _normalize_channel_name(value: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "_" for char in value.strip())
    normalized = "_".join(part for part in normalized.split("_") if part)
    if not normalized:
        return ""
    alias_key = normalized.replace("_", "")
    normalized = CHANNEL_ALIASES.get(normalized, CHANNEL_ALIASES.get(alias_key, normalized))
    if normalized in NON_MEDIA_CHANNEL_PREFIXES:
        return ""
    return normalized


def _validation_badges(detected: DetectedColumns, row_count: int) -> list[dict[str, str]]:
    badges = [
        {
            "status": "valid" if detected.time_candidates else "error",
            "label": "Date/time column detected" if detected.time_candidates else "Date/time column missing",
        },
        {
            "status": "valid" if detected.kpi_candidates else "error",
            "label": "KPI candidate detected" if detected.kpi_candidates else "KPI candidate missing",
        },
        {
            "status": "valid" if detected.spend_channel_candidates else "error",
            "label": "Spend columns detected" if detected.spend_channel_candidates else "Spend columns missing",
        },
        {
            "status": "valid" if detected.media_activity_candidates else "warning",
            "label": "Media activity columns detected" if detected.media_activity_candidates else "Media activity columns absent",
        },
        {
            "status": "valid" if detected.revenue_candidates else "warning",
            "label": "Revenue column detected" if detected.revenue_candidates else "Revenue column absent; revenue_per_kpi may be required",
        },
        {
            "status": "valid" if detected.geo_candidates and detected.population_candidates else "info",
            "label": "Geo/population detected" if detected.geo_candidates and detected.population_candidates else "Geo/population optional or absent",
        },
    ]
    if row_count < 12:
        badges.append(
            {
                "status": "warning",
                "label": f"Only {row_count} rows detected; this is likely too few for a real Meridian run",
            }
        )
    return badges


def profile_csv(upload_id: str, filename: str, path: Path) -> CsvProfile:
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError as exc:
        raise ValueError("The CSV is empty or has no readable columns.") from exc
    except UnicodeDecodeError as exc:
        raise ValueError("The file is not valid UTF-8 text. Please export the dataset as a CSV.") from exc
    except pd.errors.ParserError as exc:
        raise ValueError(f"The CSV could not be parsed: {exc}") from exc

    if df.empty and not len(df.columns):
        raise ValueError("The CSV is empty or has no readable columns.")

    columns = [
        ColumnProfile(
            name=name,
            inferred_type=_infer_type(df[name]),
            null_rate=round(float(df[name].isna().mean()), 6),
            sample_values=_sample_values(df[name]),
        )
        for name in df.columns
    ]
    detected = _detect_columns(list(df.columns))
    return CsvProfile(
        upload_id=upload_id,
        filename=filename,
        storage_path=str(path),
        row_count=int(len(df)),
        columns=columns,
        detected=detected,
        validation_badges=_validation_badges(detected, int(len(df))),
    )
