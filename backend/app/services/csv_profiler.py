from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.schemas.upload import (
    ChannelDiagnostic,
    ColumnProfile,
    CsvProfile,
    DateProfile,
    DetectedColumns,
    ReadinessCheck,
    ReadinessSummary,
)

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
MIN_MERIDIAN_MODELING_PERIODS = 52
SEVERE_CORRELATION_THRESHOLD = 0.95


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


def _summary_status(checks: list[ReadinessCheck]) -> str:
    statuses = {check.status for check in checks}
    if "error" in statuses:
        return "error"
    if "warning" in statuses:
        return "warning"
    if "valid" in statuses:
        return "valid"
    return "info"


def _schema_readiness(
    detected: DetectedColumns,
    date_profile: DateProfile,
    channel_diagnostics: list[ChannelDiagnostic],
) -> ReadinessSummary:
    media_channels = {item["channel"] for item in detected.media_activity_candidates}
    spend_channels = {item["channel"] for item in detected.spend_channel_candidates}
    paired_channels = sorted(media_channels & spend_channels)
    checks = [
        ReadinessCheck(
            code="time_column",
            label="Time column available",
            status="valid" if detected.time_candidates else "error",
            message="Date/time column detected" if detected.time_candidates else date_profile.message,
        ),
        ReadinessCheck(
            code="kpi_column",
            label="KPI column available",
            status="valid" if detected.kpi_candidates else "error",
            message="KPI candidate detected" if detected.kpi_candidates else "KPI candidate missing",
        ),
        ReadinessCheck(
            code="media_columns",
            label="Media columns available",
            status="valid" if media_channels else "error",
            message="Media activity columns detected" if media_channels else "Media activity columns missing",
        ),
        ReadinessCheck(
            code="matching_spend_columns",
            label="Matching spend columns available",
            status="valid" if paired_channels else "error",
            message="Media activity and spend pairs detected" if paired_channels else "No media columns have matching spend columns",
        ),
        ReadinessCheck(
            code="revenue_or_kpi_type",
            label="Revenue per KPI or KPI type handled",
            status="valid" if detected.revenue_candidates or detected.revenue_per_kpi_candidates else "warning",
            message=_revenue_detection_label(detected),
        ),
    ]
    return ReadinessSummary(status=_summary_status(checks), checks=checks)


def _modeling_readiness(
    df: pd.DataFrame,
    detected: DetectedColumns,
    date_profile: DateProfile,
    channel_diagnostics: list[ChannelDiagnostic],
    row_count: int,
) -> ReadinessSummary:
    active_channels = [item for item in channel_diagnostics if item.include_in_model]
    media_columns = [item.media_column or item.spend_column for item in active_channels if item.media_column or item.spend_column]
    spend_columns = [item.spend_column for item in active_channels if item.spend_column]
    required_columns = [
        *(detected.time_candidates[:1]),
        *(detected.kpi_candidates[:1]),
        *media_columns,
        *spend_columns,
    ]
    checks: list[ReadinessCheck] = []

    if row_count == 0:
        checks.append(
            ReadinessCheck(
                code="enough_history",
                label="Enough historical time periods",
                status="error",
                message="This CSV has headers but no data rows. It can be used as a blank template, but it is not large enough for Meridian modeling.",
            )
        )
    elif row_count < MIN_MERIDIAN_MODELING_PERIODS:
        checks.append(
            ReadinessCheck(
                code="enough_history",
                label="Enough historical time periods",
                status="error",
                message="This file is valid for schema mapping, but it is not large enough for Meridian modeling. Please upload a longer historical dataset.",
            )
        )
    else:
        checks.append(ReadinessCheck(code="enough_history", label="Enough historical time periods", status="valid", message="Enough historical time periods"))

    if date_profile.inferred_frequency == "weekly":
        checks.append(ReadinessCheck(code="weekly_spacing", label="Weekly date spacing", status="valid", message="Weekly date spacing detected"))
    elif date_profile.status == "valid":
        checks.append(
            ReadinessCheck(
                code="weekly_spacing",
                label="Weekly date spacing",
                status="warning",
                message=f"Date spacing appears to be {date_profile.inferred_frequency or 'irregular'}, not weekly",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                code="weekly_spacing",
                label="Weekly date spacing",
                status="error",
                message="Weekly date spacing could not be verified because the time column is missing or invalid.",
            )
        )

    missing_required = [
        column
        for column in dict.fromkeys(required_columns)
        if column in df.columns and df[column].isna().any()
    ]
    checks.append(
        ReadinessCheck(
            code="missing_required_values",
            label="No missing required values",
            status="error" if missing_required else "valid",
            message=f"Missing required values in {', '.join(missing_required[:4])}" if missing_required else "No missing required values",
        )
    )

    negative_columns = [
        column
        for column in dict.fromkeys([*(detected.kpi_candidates[:1]), *media_columns, *spend_columns])
        if column in df.columns and (pd.to_numeric(df[column], errors="coerce") < 0).any()
    ]
    checks.append(
        ReadinessCheck(
            code="non_negative_values",
            label="KPI, spend, and media values are non-negative",
            status="error" if negative_columns else "valid",
            message=f"Negative KPI/spend/media values in {', '.join(negative_columns[:4])}" if negative_columns else "KPI, spend, and media values are non-negative",
        )
    )

    low_variation_columns = []
    for column in dict.fromkeys([*media_columns, *spend_columns]):
        if column not in df.columns:
            continue
        numeric = pd.to_numeric(df[column], errors="coerce").dropna()
        if len(numeric) and numeric.nunique() < max(4, min(10, len(numeric) // 10)):
            low_variation_columns.append(column)
    checks.append(
        ReadinessCheck(
            code="sufficient_variation",
            label="Media variables have sufficient variation",
            status="warning" if low_variation_columns else "valid",
            message=f"Media/spend variables have low variation: {', '.join(low_variation_columns[:4])}" if low_variation_columns else "Media variables have sufficient variation",
        )
    )

    severe_pairs = _severe_correlation_pairs(df, detected, media_columns)
    if severe_pairs:
        checks.append(
            ReadinessCheck(
                code="high_correlation",
                label="No severe high-correlation / multicollinearity warning",
                status="warning",
                message="Several media/control variables appear highly correlated. Meridian may fail diagnostics or produce unstable estimates. Consider combining channels, removing redundant controls, or using geo-level data.",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                code="high_correlation",
                label="No severe high-correlation / multicollinearity warning",
                status="valid",
                message="No severe high-correlation / multicollinearity warning",
            )
        )

    control_collinear = _control_collinearity_pairs(df, detected, media_columns)
    checks.append(
        ReadinessCheck(
            code="control_collinearity",
            label="Controls are not perfectly collinear with media or time",
            status="warning" if control_collinear else "valid",
            message=f"Controls are highly collinear with media or time: {', '.join(control_collinear[:3])}" if control_collinear else "Controls are not perfectly collinear with media or time",
        )
    )
    return ReadinessSummary(status=_summary_status(checks), checks=checks)


def _legacy_validation_badges(schema_readiness: ReadinessSummary, modeling_readiness: ReadinessSummary) -> list[dict[str, str]]:
    return [
        {"status": check.status, "label": check.message}
        for check in [*schema_readiness.checks, *modeling_readiness.checks]
    ]


def _severe_correlation_pairs(df: pd.DataFrame, detected: DetectedColumns, media_columns: list[str | None]) -> list[str]:
    columns = [
        column
        for column in dict.fromkeys([*(column for column in media_columns if column), *detected.control_candidates])
        if column in df.columns
    ]
    return _correlated_pairs(df, columns, SEVERE_CORRELATION_THRESHOLD)


def _control_collinearity_pairs(df: pd.DataFrame, detected: DetectedColumns, media_columns: list[str | None]) -> list[str]:
    if not detected.control_candidates:
        return []
    media_cols = [column for column in media_columns if column and column in df.columns]
    compare_columns = [*media_cols]
    if detected.time_candidates:
        time_col = detected.time_candidates[0]
        if time_col in df.columns:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                parsed = pd.to_datetime(df[time_col], errors="coerce")
            if parsed.notna().any():
                df = df.copy()
                df["__time_index__"] = (parsed - parsed.min()).dt.days
                compare_columns.append("__time_index__")

    flagged: list[str] = []
    for control in detected.control_candidates:
        if control not in df.columns:
            continue
        pairs = _correlated_pairs(df, [control, *compare_columns], 0.98)
        flagged.extend(pair for pair in pairs if control in pair)
    return flagged


def _correlated_pairs(df: pd.DataFrame, columns: list[str], threshold: float) -> list[str]:
    numeric = pd.DataFrame({column: pd.to_numeric(df[column], errors="coerce") for column in dict.fromkeys(columns) if column in df.columns})
    usable = numeric.dropna(axis=1, how="all")
    usable = usable.loc[:, usable.nunique(dropna=True) > 1]
    if usable.shape[1] < 2:
        return []
    corr = usable.corr().abs()
    flagged: list[str] = []
    for idx, left in enumerate(corr.columns):
        for right in corr.columns[idx + 1 :]:
            value = corr.loc[left, right]
            if pd.notna(value) and float(value) >= threshold:
                flagged.append(f"{left} + {right}")
    return flagged


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
    schema_readiness = _schema_readiness(detected, date_profile, channel_diagnostics)
    modeling_readiness = _modeling_readiness(df, detected, date_profile, channel_diagnostics, int(len(df)))
    return CsvProfile(
        upload_id=upload_id,
        filename=filename,
        storage_path=str(path),
        row_count=int(len(df)),
        columns=columns,
        detected=detected,
        date_profile=date_profile,
        channel_diagnostics=channel_diagnostics,
        schema_readiness=schema_readiness,
        modeling_readiness=modeling_readiness,
        validation_badges=_legacy_validation_badges(schema_readiness, modeling_readiness),
    )
