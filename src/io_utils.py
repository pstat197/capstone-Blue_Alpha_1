# src/io_utils.py
import argparse
import os
import pandas as pd
from typing import List, Tuple

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "prior_sigma": "roi_prior_sigma",
        "sigma": "roi_prior_sigma",
        "roi_sigma": "roi_prior_sigma",
        "roi_prior_sd": "roi_prior_sigma",

        "prior_mu": "roi_prior_mu",
        "mu": "roi_prior_mu",
        "roi_mu": "roi_prior_mu",

        "dist": "roi_prior_dist",
        "prior_dist": "roi_prior_dist",
        "roi_dist": "roi_prior_dist",

        "channel": "target_channel",
        "target": "target_channel",
    }

    for old, new in rename_map.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})

    for col in ["target_channel", "roi_prior_mu", "roi_prior_sigma", "roi_prior_dist"]:
        if col not in df.columns:
            df[col] = pd.NA

    return df

def parse_channels_and_output(
    *,
    full_channels: List[str],
    output_dir: str,
    default_target: str = "tiktok",
) -> Tuple[List[str], str]:
    """
    Parse CLI args and return:
      - target_channels_to_run: list[str]
      - output_file: absolute output CSV path
    """

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--channels",
        nargs="+",
        default=[default_target],
        help='Target channels to run. Example: --channels tiktok OR --channels meta google. Use "all" for all.',
    )
    args = parser.parse_args()

    if len(args.channels) == 1 and str(args.channels[0]).lower() == "all":
        target_channels_to_run = full_channels
        tag = "all"
    else:
        target_channels_to_run = args.channels
        tag = "_".join(target_channels_to_run)

    output_file = os.path.join(output_dir, f"prior_sensitivity_results_{tag}.csv")
    return target_channels_to_run, output_file