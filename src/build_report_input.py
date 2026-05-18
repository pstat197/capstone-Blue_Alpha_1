from __future__ import annotations

import argparse

import pandas as pd

from src.io_utils import EXPERIMENT_METADATA_COLUMNS, STRUCTURAL_COLUMNS
from src.output_paths import report_input_csv_path, roi_csv_path, run_csv_path, tornado_csv_path


def _boolish(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def _ensure_inferable_baseline_flags(df: pd.DataFrame) -> pd.DataFrame:
    required = {"target_channel", "roi_prior_mu", "roi_prior_sigma", "roi_prior_dist", "is_baseline"}
    if not required.issubset(df.columns) or df.empty:
        return df

    repaired = df.copy()
    repaired["is_baseline"] = _boolish(repaired["is_baseline"])
    group_cols = ["target_channel", "roi_prior_dist"]
    for _, group in repaired.groupby(group_cols, dropna=False):
        if group["is_baseline"].any():
            continue
        mu_values = pd.to_numeric(group["roi_prior_mu"], errors="coerce")
        sigma_values = pd.to_numeric(group["roi_prior_sigma"], errors="coerce")
        if mu_values.notna().any() and sigma_values.notna().any():
            mu0 = mu_values.min()
            sigma0 = sigma_values.min()
            mask = mu_values.eq(mu0) & sigma_values.eq(sigma0)
            repaired.loc[group.index[mask], "is_baseline"] = True
    return repaired


def build_report_input_csv(tag: str) -> tuple[object, dict]:
    run_csv = run_csv_path(tag)
    roi_csv = roi_csv_path(tag)
    if not run_csv.exists():
        raise FileNotFoundError(f"Missing run CSV for dashboard: {run_csv}")
    if not roi_csv.exists():
        raise FileNotFoundError(f"Missing ROI CSV for dashboard: {roi_csv}")

    out_csv = report_input_csv_path(tag)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    run_df = pd.read_csv(run_csv)
    roi_df = pd.read_csv(roi_csv)
    run_df = _ensure_inferable_baseline_flags(run_df)
    roi_df = _ensure_inferable_baseline_flags(roi_df)
    tornado_csv = tornado_csv_path(tag)

    if "run_id" not in run_df.columns or "run_id" not in roi_df.columns:
        raise ValueError("Both run and ROI CSVs must include 'run_id'.")
    if "target_channel" not in run_df.columns and "targets" in run_df.columns:
        run_df["target_channel"] = run_df["targets"]

    run_base_cols = [
        "run_id",
        "target_channel",
        "roi_prior_mu",
        "roi_prior_sigma",
        "roi_prior_dist",
    ]
    missing_run = [c for c in run_base_cols if c not in run_df.columns]
    if missing_run:
        raise ValueError(f"Run CSV missing required dashboard columns: {missing_run}")

    run_extra_cols = [
        c
        for c in [
            "prior_key",
            "targets",
            "is_baseline",
            *STRUCTURAL_COLUMNS,
            *EXPERIMENT_METADATA_COLUMNS,
        ]
        if c in run_df.columns
    ]
    run_extra_cols.extend([c for c in run_df.columns if c.startswith("qc_")])
    run_extra_cols.extend([c for c in run_df.columns if c.startswith("data_")])
    run_cols = run_base_cols + run_extra_cols

    for col in ["channel", "estimated_roi"]:
        if col not in roi_df.columns:
            raise ValueError(f"ROI CSV missing required dashboard column: {col}")

    run_meta = run_df[run_cols].drop_duplicates(subset=["run_id"]).copy()
    run_merge_cols = ["run_id"]
    for col in run_meta.columns:
        if col == "run_id":
            continue
        if col.startswith("qc_") or (col not in roi_df.columns):
            run_merge_cols.append(col)
    run_meta = run_meta[run_merge_cols].copy()

    merged = roi_df.merge(run_meta, on="run_id", how="left")

    if tornado_csv.exists():
        tornado_df = pd.read_csv(tornado_csv)
        if {"run_id", "channel"}.issubset(tornado_df.columns):
            tcols = [
                "run_id",
                "channel",
                "roi_baseline",
                "roi_new",
                "delta_abs",
                "delta_pct",
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
            tcols = [c for c in tcols if c in tornado_df.columns]
            if tcols:
                tmeta = tornado_df[tcols].drop_duplicates(subset=["run_id", "channel"]).copy()
                merged = merged.merge(tmeta, on=["run_id", "channel"], how="left")

    keep_cols = [
        "run_id",
        "channel",
        "target_channel",
        "is_target_channel",
        "roi_prior_mu",
        "roi_prior_sigma",
        "roi_prior_dist",
        "prior_roi_mu_channel",
        "prior_roi_sigma_channel",
        "prior_roi_dist_channel",
        "estimated_roi",
        "posterior_roi_sd",
        "posterior_roi_p05",
        "posterior_roi_p25",
        "posterior_roi_p50",
        "posterior_roi_p75",
        "posterior_roi_p95",
        "prior_posterior_kl_gaussian",
        "prior_posterior_wasserstein",
    ]
    keep_cols.extend([c for c in run_extra_cols if c in merged.columns])
    keep_cols.extend(
        [
            c
            for c in [
                "roi_baseline",
                "roi_new",
                "delta_abs",
                "delta_pct",
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
            if c in merged.columns
        ]
    )
    merged = merged[[c for c in keep_cols if c in merged.columns]].copy()
    merged.to_csv(out_csv, index=False)

    source_files = {
        "report_input": str(out_csv),
        "runs_csv": str(run_csv),
        "roi_csv": str(roi_csv),
        "tornado_csv": str(tornado_csv) if tornado_csv.exists() else None,
    }
    return out_csv, source_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Build dashboard/report input CSV from split sensitivity outputs.")
    parser.add_argument("--tag", required=True, help="Output tag to read from data/output/01_runs/<tag>.")
    args = parser.parse_args()

    out_csv, source_files = build_report_input_csv(str(args.tag))
    print("Report input table ready:", out_csv)
    print("Source runs CSV:", source_files.get("runs_csv"))
    print("Source ROI CSV:", source_files.get("roi_csv"))
    if source_files.get("tornado_csv"):
        print("Source tornado CSV:", source_files.get("tornado_csv"))


if __name__ == "__main__":
    main()
