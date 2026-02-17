import pandas as pd
from typing import Tuple
from config import DataConfig

def load_raw_data(cfg: DataConfig) -> pd.DataFrame:
    df = pd.read_csv(cfg.raw_path)
    return df

def validate_columns(df: pd.DataFrame, cfg: DataConfig) -> None:
    required = [cfg.time_col, cfg.kpi_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    if cfg.revenue_per_kpi_col and cfg.revenue_per_kpi_col not in df.columns:
        raise ValueError(f"revenue_per_kpi_col not found: {cfg.revenue_per_kpi_col}")

    for group_name, cols in [
        ("control_cols", cfg.control_cols),
        ("media_cols", cfg.media_cols),
        ("media_spend_cols", cfg.media_spend_cols),
        ("organic_cols", cfg.organic_cols),
        ("reach_cols", cfg.reach_cols),
        ("frequency_cols", cfg.frequency_cols),
    ]:
        if cols:
            missing_cols = [c for c in cols if c not in df.columns]
            if missing_cols:
                raise ValueError(f"Missing {group_name}: {missing_cols}")

def basic_cleaning(df: pd.DataFrame, cfg: DataConfig) -> pd.DataFrame:
    out = df.copy()
    out[cfg.time_col] = pd.to_datetime(out[cfg.time_col], errors="ignore")
    out = out.sort_values(cfg.time_col)

    if out[cfg.time_col].duplicated().any():
        raise ValueError("Duplicate time values detected. MMM typically needs one row per time period.")

    if out[cfg.kpi_col].isna().any():
        raise ValueError("Missing values in KPI column. Fill/impute or remove before modeling.")

    return out

def prepare_dataset(cfg: DataConfig) -> pd.DataFrame:
    df = load_raw_data(cfg)
    validate_columns(df, cfg)
    df = basic_cleaning(df, cfg)
    return df
