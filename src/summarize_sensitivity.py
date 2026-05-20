# src/summarize_sensitivity.py
import os
import sys
import subprocess
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

from src.output_paths import (
    TABLES_DIR,
    ensure_output_dirs,
    roi_csv_path,
    run_csv_path,
    tornado_csv_path,
)
from src.io_utils import EXPERIMENT_METADATA_COLUMNS, STRUCTURAL_COLUMNS


def _pick_center(values):
    vals = sorted(pd.Series(values).dropna().unique().tolist())
    if not vals:
        return None
    return vals[len(vals) // 2]


def _baseline_scope_columns(df: pd.DataFrame) -> list[str]:
    cols = ["targets"]
    scenario_cols = [
        "kpi_type",
        "kpi_type_effective",
        "outcome_col_used",
        "revenue_per_kpi",
        "prior_design_mode",
        "prior_grid_type",
        "prior_design_label",
        "input_data_csv",
    ]
    cols.extend([c for c in scenario_cols if c in df.columns])
    return cols


def _infer_baseline_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Fallback baseline inference when is_baseline flag is missing/empty.

    Uses center-point prior values (middle mu, middle sigma, preferred dist)
    per baseline scope group.
    """
    if df.empty:
        return df.copy()

    required = {"targets", "roi_prior_mu", "roi_prior_sigma", "roi_prior_dist"}
    if not required.issubset(df.columns):
        return df.iloc[0:0].copy()

    picked = []
    group_cols = _baseline_scope_columns(df)
    for _, g in df.groupby(group_cols, dropna=False):
        mu0 = _pick_center(g["roi_prior_mu"])
        sigma0 = _pick_center(g["roi_prior_sigma"])
        dists = [str(x) for x in g["roi_prior_dist"].dropna().unique().tolist()]
        dist0 = "LogNormal" if "LogNormal" in dists else (_pick_center(dists) if dists else None)
        if mu0 is None or sigma0 is None:
            continue

        mask = np.isclose(pd.to_numeric(g["roi_prior_mu"], errors="coerce"), float(mu0))
        mask &= np.isclose(pd.to_numeric(g["roi_prior_sigma"], errors="coerce"), float(sigma0))
        if dist0 is not None:
            mask &= g["roi_prior_dist"].astype(str).eq(str(dist0))

        gg = g[mask].copy()
        if not gg.empty:
            picked.append(gg)

    if not picked:
        return df.iloc[0:0].copy()
    return pd.concat(picked, ignore_index=True)


def _paths_for_tag(tag: str) -> dict[str, Path]:
    return {
        "run_csv": run_csv_path(tag),
        "roi_csv": roi_csv_path(tag),
        "tornado_csv": tornado_csv_path(tag, TABLES_DIR),
    }


def _sanitize_tag_token(raw: str) -> str:
    s = str(raw).strip().lower()
    out = []
    for ch in s:
        if ch.isalnum() or ch in {"-", "_"}:
            out.append(ch)
        else:
            out.append("_")
    token = "".join(out).strip("_")
    while "__" in token:
        token = token.replace("__", "_")
    return token or "dataset"


def _safe_read_csv_or_backup(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except pd.errors.ParserError:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_name(f"{path.name}.corrupt_backup_{stamp}.csv")
        os.replace(path, backup)
        print(
            "[warn] Found malformed CSV (likely mixed schemas). "
            f"Moved to backup: {backup}"
        )
        return pd.DataFrame()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.set_defaults(dollars_per_subscription=100.0)
    parser.add_argument("targets", nargs="+")
    parser.add_argument(
        "--dps",
        dest="dollars_per_subscription",
        type=float,
        help="Dollar value for one subscription. Defaults to 100.",
    )
    parser.add_argument(
        "--dollars_per_subscription",
        type=float,
        dest="dollars_per_subscription",
        help=(
            "Optional dollar value for one subscription. When provided, the tornado output "
            "also includes dollar-value columns."
        ),
    )
    parser.add_argument(
        "--value_per_kpi",
        dest="dollars_per_subscription",
        type=float,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Optional output tag to read/write instead of the target-derived tag.",
    )
    return parser


def _load_channel_spend(project_root: str, channels: list[str], data_csv: str | None = None) -> pd.DataFrame:
    if data_csv is None:
        data_csv = os.path.join(project_root, "data", "raw", "monthly_mocha.csv")
    if not os.path.isabs(data_csv):
        data_csv = os.path.join(project_root, data_csv)
    if not os.path.exists(data_csv):
        local_data_csv = os.path.join(project_root, "data", "raw", os.path.basename(data_csv.replace("\\", "/")))
        if os.path.exists(local_data_csv):
            data_csv = local_data_csv
    if not os.path.exists(data_csv):
        raise FileNotFoundError(
            f"Data CSV for channel spend totals not found: {data_csv}. "
            "Set input_data_csv metadata or provide the expected dataset path."
        )
    raw_df = pd.read_csv(data_csv)
    cols_by_lower = {str(column).lower(): str(column) for column in raw_df.columns}

    records = []
    for channel in channels:
        spend_col = f"{channel}_spend"
        resolved_spend_col = spend_col if spend_col in raw_df.columns else cols_by_lower.get(spend_col.lower())
        if resolved_spend_col:
            spend_total = float(pd.to_numeric(raw_df[resolved_spend_col], errors="coerce").fillna(0).sum())
            records.append({"channel": channel, "channel_total_spend": spend_total})

    return pd.DataFrame(records)


def _load_current_results(paths: dict[str, Path]) -> pd.DataFrame:
    run_csv = paths["run_csv"]
    roi_csv = paths["roi_csv"]
    if not run_csv.exists() or not roi_csv.exists():
        return pd.DataFrame()

    run_df = _safe_read_csv_or_backup(run_csv)
    roi_df = _safe_read_csv_or_backup(roi_csv)
    if run_df.empty or roi_df.empty:
        return pd.DataFrame()

    if "run_id" not in run_df.columns or "run_id" not in roi_df.columns:
        raise ValueError("Current split outputs must include 'run_id' in both run and ROI CSVs.")

    run_cols = [
        c for c in [
            "run_id",
            "prior_key",
            "targets",
            "roi_prior_mu",
            "roi_prior_sigma",
            "roi_prior_dist",
            *STRUCTURAL_COLUMNS,
            *EXPERIMENT_METADATA_COLUMNS,
            "is_baseline",
            "qc_status_code",
            "qc_summary_short",
            "qc_primary_review_check",
            "qc_flagged_channels",
        ] if c in run_df.columns
    ]
    run_meta = run_df[run_cols].drop_duplicates(subset=["run_id"]).copy()
    return roi_df.merge(run_meta, on="run_id", how="left", suffixes=("", "_run"))


def _filter_to_prior_stage(df: pd.DataFrame) -> pd.DataFrame:
    if "analysis_stage" not in df.columns:
        return df.copy()
    mask = df["analysis_stage"].astype(str).str.strip().str.lower() == "prior_sweep"
    filtered = df.loc[mask].copy()
    return filtered if not filtered.empty else df.copy()


def main():
    parser = _build_parser()
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ensure_output_dirs()

    targets = args.targets
    if len(targets) < 1:
        raise ValueError(
            "Usage:\n"
            "  python -m src.summarize_sensitivity <target1> [target2 ...]\n"
            "Example:\n"
            "  python -m src.summarize_sensitivity meta\n"
            "  python -m src.summarize_sensitivity meta google"
        )

    targets_sorted = sorted([str(t) for t in targets])
    tag = _sanitize_tag_token(args.tag) if args.tag else "_".join(targets_sorted)

    paths = _paths_for_tag(tag)
    out_csv = paths["tornado_csv"]
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    df = _load_current_results(paths)

    # Auto-run src.main --targets ... if results missing
    if df.empty:
        cmd = [sys.executable, "-m", "src.main", "--targets"] + targets_sorted

        print("Sensitivity outputs missing; running sensitivity first.")

        proc = subprocess.run(cmd, cwd=project_root)
        if proc.returncode != 0:
            raise RuntimeError(f"Auto-run of src.main failed with exit code {proc.returncode}")

        df = _load_current_results(paths)
        if df.empty:
            raise FileNotFoundError(
                "Expected split outputs not found after auto-run: "
                f"{paths['run_csv']} / {paths['roi_csv']}"
            )

    # Summarize
    # Match targets string inside file
    targets_str = ",".join(targets_sorted)
    if "targets" not in df.columns:
        raise ValueError("Input CSV has no 'targets' column; cannot summarize multi-prior results.")
    target_matched = df[df["targets"] == targets_str].copy()
    if target_matched.empty and "target_channel" in df.columns:
        target_set = set(targets_sorted)
        target_matched = df[df["target_channel"].astype(str).isin(target_set)].copy()
    df = target_matched
    df = _filter_to_prior_stage(df)

    if "is_baseline" not in df.columns:
        raise ValueError("Missing column 'is_baseline' in results CSV. Cannot identify baseline reliably.")

    baseline_mask = df["is_baseline"].astype(str).str.lower().isin({"true", "1", "yes"})
    baseline_df = df[baseline_mask].copy()
    baseline_run_ids = None
    if baseline_df.empty:
        baseline_df = _infer_baseline_rows(df)
        if baseline_df.empty:
            raise ValueError(
                "No baseline rows found (is_baseline==True), and fallback inference failed. "
                "Check baseline settings in main.py or ensure baseline prior combo exists in the CSV."
            )
        if "run_id" in baseline_df.columns:
            baseline_run_ids = set(baseline_df["run_id"].dropna().astype(str).tolist())
        print("[warn] No explicit baseline rows found; inferred baseline from center prior values.")
    baseline_metric_rename = {
        "estimated_roi": "roi_baseline",
        "posterior_roi_sd": "roi_baseline_sd",
        "posterior_roi_p05": "roi_baseline_p05",
        "posterior_roi_p50": "roi_baseline_p50",
        "posterior_roi_p95": "roi_baseline_p95",
    }
    baseline_metric_cols = [c for c in baseline_metric_rename if c in baseline_df.columns]
    if not baseline_metric_cols:
        raise ValueError("Baseline rows are missing ROI metrics needed for tornado summarization.")
    baseline_group_cols = _baseline_scope_columns(df)
    baseline_join_cols = [*baseline_group_cols, "channel"]
    baseline_summary = (
        baseline_df.groupby(baseline_join_cols, dropna=False)[baseline_metric_cols]
        .mean()
        .reset_index()
        .rename(columns=baseline_metric_rename)
    )

    df = df.merge(baseline_summary, on=baseline_join_cols, how="left")
    df["roi_new"] = df["estimated_roi"]
    df["delta_abs"] = (df["roi_new"] - df["roi_baseline"]).abs()
    df["delta_pct"] = np.where(
        df["roi_baseline"] != 0,
        ((df["roi_new"] / df["roi_baseline"]) - 1).abs(),
        np.nan
    )

    if "posterior_roi_p05" in df.columns:
        df["roi_new_p05"] = pd.to_numeric(df["posterior_roi_p05"], errors="coerce")
    if "posterior_roi_p50" in df.columns:
        df["roi_new_p50"] = pd.to_numeric(df["posterior_roi_p50"], errors="coerce")
    if "posterior_roi_p95" in df.columns:
        df["roi_new_p95"] = pd.to_numeric(df["posterior_roi_p95"], errors="coerce")
    if "posterior_roi_sd" in df.columns:
        df["roi_new_sd"] = pd.to_numeric(df["posterior_roi_sd"], errors="coerce")

    if {"roi_baseline_p05", "roi_baseline_p95", "roi_new_p05", "roi_new_p95"}.issubset(df.columns):
        lo_base = pd.to_numeric(df["roi_baseline_p05"], errors="coerce")
        hi_base = pd.to_numeric(df["roi_baseline_p95"], errors="coerce")
        lo_new = pd.to_numeric(df["roi_new_p05"], errors="coerce")
        hi_new = pd.to_numeric(df["roi_new_p95"], errors="coerce")
        overlap = np.maximum(0.0, np.minimum(hi_base, hi_new) - np.maximum(lo_base, lo_new))
        union = np.maximum(hi_base, hi_new) - np.minimum(lo_base, lo_new)
        df["ci_overlap_baseline_new"] = np.where(union > 0, overlap / union, np.nan)

    input_data_csv = None
    if "input_data_csv" in df.columns:
        non_null = df["input_data_csv"].dropna().astype(str).str.strip()
        non_null = non_null[non_null != ""]
        if not non_null.empty:
            input_data_csv = non_null.iloc[0]
    spend_df = _load_channel_spend(
        project_root,
        sorted(df["channel"].dropna().astype(str).unique().tolist()),
        data_csv=input_data_csv,
    )
    if not spend_df.empty:
        df = df.merge(spend_df, on="channel", how="left")
        df["channel_total_spend"] = pd.to_numeric(df["channel_total_spend"], errors="coerce")
        df["incremental_outcome_baseline"] = df["roi_baseline"] * df["channel_total_spend"]
        df["incremental_outcome_new"] = df["roi_new"] * df["channel_total_spend"]
        df["delta_outcome"] = df["incremental_outcome_new"] - df["incremental_outcome_baseline"]
        df["delta_outcome_abs"] = df["delta_outcome"].abs()

        dollars_per_subscription = float(args.dollars_per_subscription)
        df["dollars_per_subscription"] = dollars_per_subscription
        df["incremental_value_baseline"] = df["incremental_outcome_baseline"] * dollars_per_subscription
        df["incremental_value_new"] = df["incremental_outcome_new"] * dollars_per_subscription
        df["delta_value"] = df["incremental_value_new"] - df["incremental_value_baseline"]
        df["delta_value_abs"] = df["delta_value"].abs()

    # remove baseline rows
    if baseline_run_ids is not None and "run_id" in df.columns:
        df = df[~df["run_id"].astype(str).isin(baseline_run_ids)].copy()
    else:
        non_baseline_mask = df["is_baseline"].astype(str).str.lower().isin({"false", "0", "no"})
        df = df[non_baseline_mask].copy()
    if df.empty:
        print(
            "[warn] No non-baseline rows available for tornado scoring. "
            "Run at least one additional grid point beyond baseline."
        )

    required_cols = [
        "run_id",
        "targets",
        "prior_key",
        "channel",
        "qc_status_code",
        "qc_summary_short",
        "qc_primary_review_check",
        "qc_flagged_channels",
        "roi_baseline",
        "roi_new",
        "delta_abs",
        "delta_pct",
    ]
    optional_cols = [
        *STRUCTURAL_COLUMNS,
        *EXPERIMENT_METADATA_COLUMNS,
        "roi_prior_mu",
        "roi_prior_sigma",
        "roi_prior_dist",
        "roi_baseline_sd",
        "roi_baseline_p05",
        "roi_baseline_p50",
        "roi_baseline_p95",
        "roi_new_sd",
        "roi_new_p05",
        "roi_new_p50",
        "roi_new_p95",
        "ci_overlap_baseline_new",
        "prior_roi_mu_channel",
        "prior_roi_sigma_channel",
        "prior_roi_dist_channel",
        "prior_posterior_kl_gaussian",
        "prior_posterior_wasserstein",
        "channel_total_spend",
        "incremental_outcome_baseline",
        "incremental_outcome_new",
        "delta_outcome",
        "delta_outcome_abs",
        "dollars_per_subscription",
        "incremental_value_baseline",
        "incremental_value_new",
        "delta_value",
        "delta_value_abs",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in results CSV: {missing}")

    output_cols = required_cols + [c for c in optional_cols if c in df.columns]
    df[output_cols].to_csv(out_csv, index=False)
    print("Tornado summary ready.")


if __name__ == "__main__":
    main()
