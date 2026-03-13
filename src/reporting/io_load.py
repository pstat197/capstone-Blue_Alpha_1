from __future__ import annotations
import pandas as pd
from pathlib import Path

REQUIRED_COLS = {
    "channel", "target_channel", "roi_prior_mu", "roi_prior_sigma", "roi_prior_dist", "estimated_roi"
}

def load_results(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    # Normalize dtypes
    df["roi_prior_mu"] = df["roi_prior_mu"].astype(float)
    df["roi_prior_sigma"] = df["roi_prior_sigma"].astype(float)
    df["estimated_roi"] = df["estimated_roi"].astype(float)
    df["channel"] = df["channel"].astype(str)
    df["target_channel"] = df["target_channel"].astype(str)
    df["roi_prior_dist"] = df["roi_prior_dist"].astype(str)

    return df
