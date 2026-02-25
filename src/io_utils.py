# src/io_utils.py
import argparse
import os
import pandas as pd
from typing import List, Tuple, Optional, Set, Union

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
) -> Tuple[List[str], str, Optional[List[str]]]:
    """
    Parse CLI args and return:
      - target_channels_to_run: list[str]  (single-target mode)
      - output_file: absolute output CSV path
      - targets: optional list[str]        (multi-prior mode if provided)
    """

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--channels",
        nargs="+",
        default=[default_target],
        help='Single-target mode. Example: --channels tiktok OR --channels meta google. Use "all" for all.',
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        default=None,
        help='Multi-prior mode (linked). Example: --targets meta tiktok',
    )
    args = parser.parse_args()

    # Multi-prior mode
    if args.targets is not None and len(args.targets) > 0:
        targets = [str(x) for x in args.targets]
        tag = "_".join(targets)
        output_file = os.path.join(output_dir, f"prior_sensitivity_results_multi_{tag}.csv")
        return args.channels, output_file, targets

    # Single-target mode
    if len(args.channels) == 1 and str(args.channels[0]).lower() == "all":
        target_channels_to_run = full_channels
        tag = "all"
    else:
        target_channels_to_run = args.channels
        tag = "_".join(target_channels_to_run)

    output_file = os.path.join(output_dir, f"prior_sensitivity_results_{tag}.csv")
    return target_channels_to_run, output_file, None


AlreadyDone = Union[Set[str], Set[tuple]]

def load_resume_state(output_file: str) -> AlreadyDone:
    """
    Load existing output CSV (if it exists) and return already_done.
    - If output contains 'prior_key' -> multiprior mode: already_done is Set[str]
    - Else -> single-target mode: already_done is Set[(target_channel, mu, sigma, dist)]
    """

    if not os.path.exists(output_file):
        return set()

    results_df = pd.read_csv(output_file)
    print("Existing results found. Loading...")

    results_df = normalize_columns(results_df)

    # multiprior resume-safe
    if "prior_key" in results_df.columns:
        results_df["prior_key"] = results_df["prior_key"].astype(str)
        return set(results_df["prior_key"].tolist())

    # single-target resume-safe
    results_df["roi_prior_mu"] = pd.to_numeric(results_df["roi_prior_mu"], errors="coerce").round(6)
    results_df["roi_prior_sigma"] = pd.to_numeric(results_df["roi_prior_sigma"], errors="coerce").round(6)
    results_df["roi_prior_dist"] = results_df["roi_prior_dist"].astype(str)

    return set(
        zip(
            results_df["target_channel"].astype(str),
            results_df["roi_prior_mu"],
            results_df["roi_prior_sigma"],
            results_df["roi_prior_dist"],
        )
    )


def append_tmp_to_output(
    *,
    tmp_out: str,
    output_file: str,
    ensure_cols: Optional[dict] = None,
    cast_single_target: bool = False,
) -> pd.DataFrame:
    """
    Read tmp_out CSV, normalize columns, optionally ensure metadata columns,
    append to output_file, then return the DataFrame.

    ensure_cols: dict of {col_name: value} inserted if missing
    cast_single_target: if True, force numeric rounding for roi_prior_mu/sigma and str for dist
    """

    if not os.path.exists(tmp_out):
        raise FileNotFoundError(f"Subprocess finished but output missing: {tmp_out}")

    part = pd.read_csv(tmp_out)
    part = normalize_columns(part)

    if cast_single_target:
        part["roi_prior_mu"] = pd.to_numeric(part["roi_prior_mu"], errors="coerce").round(6)
        part["roi_prior_sigma"] = pd.to_numeric(part["roi_prior_sigma"], errors="coerce").round(6)
        part["roi_prior_dist"] = part["roi_prior_dist"].astype(str)

    if ensure_cols:
        for k, v in ensure_cols.items():
            if k not in part.columns:
                part[k] = v

    write_header = (not os.path.exists(output_file)) or (os.path.getsize(output_file) == 0)
    part.to_csv(output_file, mode="a", header=write_header, index=False)
    return part