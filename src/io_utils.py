# src/io_utils.py
import argparse
import os
import pandas as pd
from typing import List, Tuple, Optional, Set, Union

RUN_OUTPUT_COLUMNS = [
    "run_id",
    "prior_key",
    "targets",
    "target_channel",
    "roi_prior_mu",
    "roi_prior_sigma",
    "roi_prior_dist",
    "is_baseline",
    "qc_status_code",
    "qc_severity_rank",
    "qc_needs_review",
    "qc_summary_short",
    "qc_primary_review_check",
    "qc_flagged_channels",
    "qc_review_reason",
    "qc_convergence_status",
    "qc_baseline_status",
    "qc_bayesianppp_status",
    "qc_gof_status",
    "qc_prior_posterior_shift_status",
    "qc_roi_consistency_status",
    "qc_r2",
    "qc_mape",
    "qc_wmape",
    "qc_bayesian_ppp",
    "qc_baseline_neg_prob",
    "qc_report_full",
]

ROI_OUTPUT_COLUMNS = [
    "run_id",
    "prior_key",
    "targets",
    "target_channel",
    "channel",
    "roi_prior_mu",
    "roi_prior_sigma",
    "roi_prior_dist",
    "is_baseline",
    "estimated_roi",
    "qc_overall_status",
    "qc_summary",
    "qc_pass_fail",
    "qc_needs_review",
    "qc_text",
    "qc_r2",
    "qc_mape",
    "qc_wmape",
    "qc_bayesian_ppp",
    "qc_baseline_neg_prob",
]

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
    default_target: Union[str, List[str]] = "tiktok",
) -> Tuple[List[str], str, Optional[List[str]]]:
    """
    Parse CLI args and return:
      - target_channels_to_run: list[str]  (linked target-set mode)
      - output_file: absolute output CSV path
      - targets: list[str]                 (same as target_channels_to_run)
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--channels",
        nargs="+",
        default=None,
        help='Deprecated alias for --targets. Example: --channels tiktok OR --channels meta google. Use "all" for all.',
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        default=None,
        help='Target set for linked multi-prior mode. Example: --targets meta tiktok',
    )
    args = parser.parse_args()

    if args.targets is not None and args.channels is not None:
        raise ValueError("Use only one of --targets or --channels (deprecated alias), not both.")

    raw_targets = args.targets if args.targets is not None else args.channels
    if raw_targets is None:
        raw_targets = default_target if isinstance(default_target, list) else [default_target]

    targets = [str(x) for x in raw_targets]
    if len(targets) == 1 and targets[0].lower() == "all":
        targets = list(full_channels)
    if len(targets) == 0:
        raise ValueError("Provide at least one target channel.")

    targets_sorted = sorted(targets)
    tag = "_".join(targets_sorted)
    output_file = os.path.join(output_dir, f"prior_sensitivity_results_multi_{tag}.csv")
    return targets_sorted, output_file, targets_sorted


AlreadyDone = Union[Set[str], Set[tuple]]

def load_resume_state(output_file: str) -> AlreadyDone:
    """
    Load existing output CSV (if it exists) and return already_done.
    - If output contains 'run_id' -> return Set[str] of completed run ids
    - Else preserve legacy resume behavior for older combined output files
    """

    if not os.path.exists(output_file):
        return set()

    results_df = pd.read_csv(output_file)
    print("Existing results found. Loading...")

    if "run_id" in results_df.columns:
        results_df["run_id"] = results_df["run_id"].astype(str)
        return set(results_df["run_id"].tolist())

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
    expected_columns: Optional[List[str]] = None,
    normalize_part: bool = True,
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
    if normalize_part:
        part = normalize_columns(part)

    if cast_single_target:
        part["roi_prior_mu"] = pd.to_numeric(part["roi_prior_mu"], errors="coerce").round(6)
        part["roi_prior_sigma"] = pd.to_numeric(part["roi_prior_sigma"], errors="coerce").round(6)
        part["roi_prior_dist"] = part["roi_prior_dist"].astype(str)

    if ensure_cols:
        for k, v in ensure_cols.items():
            if k not in part.columns:
                part[k] = v

    if expected_columns:
        for col in expected_columns:
            if col not in part.columns:
                part[col] = pd.NA
        part = part.reindex(columns=expected_columns)

    write_header = (not os.path.exists(output_file)) or (os.path.getsize(output_file) == 0)
    part.to_csv(output_file, mode="a", header=write_header, index=False)
    return part
