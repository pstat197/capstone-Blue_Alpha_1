from __future__ import annotations

import pandas as pd


BASELINE_TRUE_VALUES = {"true", "1", "yes"}


def boolish_baseline(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(BASELINE_TRUE_VALUES)


def require_explicit_baseline_rows(
    df: pd.DataFrame,
    *,
    context: str,
    require_columns: tuple[str, ...] = ("is_baseline",),
) -> None:
    missing = [col for col in require_columns if col not in df.columns]
    if missing:
        raise ValueError(
            "Explicit baseline metadata is required. "
            f"{context} is missing baseline metadata column(s): {missing}. "
            "Please regenerate the run/report with an explicit setup-confirmed baseline."
        )
    if "is_baseline" in df.columns and not boolish_baseline(df["is_baseline"]).any():
        raise ValueError(
            "Explicit baseline metadata is required. "
            f"No valid is_baseline row was found in {context}. "
            "Please regenerate the run/report with an explicit setup-confirmed baseline."
        )
