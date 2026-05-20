from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.schemas.upload import ChannelDiagnostic, ColumnProfile, CsvProfile, DateProfile, DetectedColumns

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

DIRECT_REVENUE_NAMES = {
    "revenue",
    "sales",
    "total_revenue",
    "net_revenue",
    "gross_revenue",
    "gmv",
    "income",
    "turnover",
}

REVENUE_PER_KPI_PREFIXES = (
    "revenue_per_",
    "rev_per_",
    "value_per_",
    "dollars_per_",
    "dollar_per_",
)

CONTROL_LIKE_TOKENS = ("promo", "holiday", "competitor", "control", "sentiment", "season", "price")


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


def _numeric_signal(series: pd.Series) -> tuple[float | None, float | None]:
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.notna()
    if not valid.any():
        return None, None
    nonzero_rate = float((numeric[valid] != 0).mean())
    total_value = float(numeric[valid].sum())
    return round(nonzero_rate, 6), round(total_value, 6)


def _column_profile(name: str, series: pd.Series) -> ColumnProfile:
    inferred_type = _infer_type(series)
    nonzero_rate, total_value = _numeric_signal(series)
    status = "valid"
    if inferred_type == "number" and total_value == 0:
        status = "warning"
    return ColumnProfile(
        name=name,
        inferred_type=inferred_type,
        null_rate=round(float(series.isna().mean()), 6),
        nonzero_rate=nonzero_rate,
        total_value=total_value,
        status=status,
        sample_values=_sample_values(series),
    )


def _detect_columns(column_names: list[str]) -> DetectedColumns:
    lowered = {name: name.lower() for name in column_names}
    time_candidates = [
        name
        for name, lower in lowered.items()
        if lower in {"date", "week", "month", "time", "period", "time_period"} or lower.endswith("_date")
    ]
    revenue_per_kpi_candidates = [
        name
        for name, lower in lowered.items()
        if _is_revenue_per_kpi_column(lower)
    ]
    revenue_candidates = [
        name
        for name, lower in lowered.items()
        if name not in revenue_per_kpi_candidates and _is_direct_revenue_column(lower)
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
    excluded = (
        set(time_candidates)
        | set(revenue_candidates)
        | set(revenue_per_kpi_candidates)
        | set(geo_candidates)
        | set(population_candidates)
    )
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
    direct_revenue_kpis = [name for name in revenue_candidates if lowered[name] in DIRECT_REVENUE_NAMES]
    kpi_candidates = [*direct_revenue_kpis, *[name for name in kpi_candidates if name not in direct_revenue_kpis]]

    return DetectedColumns(
        time_candidates=time_candidates,
        kpi_candidates=kpi_candidates,
        media_activity_candidates=media_activity_candidates,
        spend_channel_candidates=spend_channel_candidates,
        revenue_candidates=revenue_candidates,
        revenue_per_kpi_candidates=revenue_per_kpi_candidates,
        control_candidates=control_candidates,
        geo_candidates=geo_candidates,
        population_candidates=population_candidates,
    )


def _is_revenue_per_kpi_column(lower: str) -> bool:
    normalized = lower.replace("-", "_").replace(" ", "_")
    if _is_control_like_column(normalized):
        return False
    return normalized.startswith(REVENUE_PER_KPI_PREFIXES) or "_revenue_per_" in normalized


def _is_direct_revenue_column(lower: str) -> bool:
    normalized = lower.replace("-", "_").replace(" ", "_")
    if _is_control_like_column(normalized):
        return False
    if normalized in DIRECT_REVENUE_NAMES:
        return True
    tokens = {token for token in normalized.split("_") if token}
    return bool(tokens & {"revenue", "sales", "gmv", "income", "turnover"})


def _is_control_like_column(normalized: str) -> bool:
    return any(token in normalized for token in CONTROL_LIKE_TOKENS)


def _infer_frequency(parsed: pd.Series) -> str | None:
    dates = parsed.dropna().sort_values().drop_duplicates()
    if len(dates) < 3:
        return None
    deltas = dates.diff().dropna().dt.days
    if deltas.empty:
        return None
    median_days = float(deltas.median())
    if 6 <= median_days <= 8:
        return "weekly"
    if 27 <= median_days <= 32:
        return "monthly"
    if 13 <= median_days <= 15:
        return "biweekly"
    if 0.8 <= median_days <= 1.2:
        return "daily"
    return f"every {median_days:.0f} days"


def _date_profile(df: pd.DataFrame, detected: DetectedColumns) -> DateProfile:
    if not detected.time_candidates:
        return DateProfile(
            status="missing",
            message="Date/time column missing",
        )

    column = detected.time_candidates[0]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        parsed = pd.to_datetime(df[column], errors="coerce")
    parse_rate = round(float(parsed.notna().mean()), 6) if len(parsed) else 0
    if parse_rate == 0:
        return DateProfile(
            column=column,
            valid_parse_rate=parse_rate,
            status="warning",
            message="Date column detected but date range could not be parsed.",
        )

    date_min = parsed.min()
    date_max = parsed.max()
    return DateProfile(
        column=column,
        date_min=date_min.strftime("%Y-%m-%d"),
        date_max=date_max.strftime("%Y-%m-%d"),
        valid_parse_rate=parse_rate,
        inferred_frequency=_infer_frequency(parsed),
        status="valid" if parse_rate >= 0.8 else "warning",
        message="Date range parsed" if parse_rate >= 0.8 else "Date column detected but some rows could not be parsed.",
    )


def _column_by_name(columns: list[ColumnProfile]) -> dict[str, ColumnProfile]:
    return {column.name: column for column in columns}


def _channel_diagnostics(detected: DetectedColumns, columns: list[ColumnProfile]) -> list[ChannelDiagnostic]:
    by_name = _column_by_name(columns)
    spend_by_channel = {item["channel"]: item["column"] for item in detected.spend_channel_candidates}
    media_by_channel = {item["channel"]: item["column"] for item in detected.media_activity_candidates}
    channels = sorted(set(spend_by_channel) | set(media_by_channel))
    diagnostics: list[ChannelDiagnostic] = []

    for channel in channels:
        spend_column = spend_by_channel.get(channel)
        media_column = media_by_channel.get(channel)
        spend = by_name.get(spend_column) if spend_column else None
        media = by_name.get(media_column) if media_column else None
        spend_total = spend.total_value if spend else None
        media_total = media.total_value if media else None
        spend_has_signal = spend_total is not None and spend_total != 0
        media_has_signal = media_total is not None and media_total != 0

        if spend and spend_has_signal and media and media_has_signal:
            status = "active_paid_media"
            severity = "valid"
            include_in_model = True
            message = "Included in model"
        elif spend and spend_has_signal and not media_has_signal:
            status = "spend_as_media_fallback"
            severity = "warning"
            include_in_model = True
            message = "Spend will be used as the media unit unless remapped"
        elif spend and not spend_has_signal and not media_has_signal:
            status = "inactive_all_zero"
            severity = "warning"
            include_in_model = False
            message = "Excluded from model"
        else:
            status = "not_eligible_paid_media"
            severity = "warning"
            include_in_model = False
            message = "Classify as organic/non-media or fix spend data"

        diagnostics.append(
            ChannelDiagnostic(
                channel=channel,
                spend_column=spend_column,
                media_column=media_column,
                spend_null_rate=spend.null_rate if spend else None,
                spend_nonzero_rate=spend.nonzero_rate if spend else None,
                spend_total=spend_total,
                media_null_rate=media.null_rate if media else None,
                media_nonzero_rate=media.nonzero_rate if media else None,
                media_total=media_total,
                status=status,
                severity=severity,
                include_in_model=include_in_model,
                message=message,
            )
        )

    return diagnostics


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


def _validation_badges(detected: DetectedColumns, date_profile: DateProfile, channel_diagnostics: list[ChannelDiagnostic], row_count: int) -> list[dict[str, str]]:
    active_or_fallback = [item for item in channel_diagnostics if item.include_in_model]
    inactive = [item for item in channel_diagnostics if item.status == "inactive_all_zero"]
    badges = [
        {
            "status": date_profile.status if date_profile.status != "missing" else "error",
            "label": "Date/time column detected" if date_profile.status == "valid" else date_profile.message,
        },
        {
            "status": "valid" if detected.kpi_candidates else "error",
            "label": "KPI candidate detected" if detected.kpi_candidates else "KPI candidate missing",
        },
        {
            "status": "valid" if active_or_fallback else "error",
            "label": "Active paid channels detected" if active_or_fallback else "Active paid channels missing",
        },
        {
            "status": "warning" if inactive else "valid",
            "label": f"{len(inactive)} inactive channel excluded" if inactive else "No inactive paid channels",
        },
        {
            "status": "valid" if detected.revenue_candidates or detected.revenue_per_kpi_candidates else "warning",
            "label": _revenue_detection_label(detected),
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


def _revenue_detection_label(detected: DetectedColumns) -> str:
    if detected.revenue_candidates:
        return "Revenue column detected"
    if detected.revenue_per_kpi_candidates:
        return "Revenue-per-KPI helper detected"
    return "Revenue column not detected"


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

    columns = [_column_profile(name, df[name]) for name in df.columns]
    detected = _detect_columns(list(df.columns))
    date_profile = _date_profile(df, detected)
    channel_diagnostics = _channel_diagnostics(detected, columns)
    return CsvProfile(
        upload_id=upload_id,
        filename=filename,
        storage_path=str(path),
        row_count=int(len(df)),
        columns=columns,
        detected=detected,
        date_profile=date_profile,
        channel_diagnostics=channel_diagnostics,
        validation_badges=_validation_badges(detected, date_profile, channel_diagnostics, int(len(df))),
    )
