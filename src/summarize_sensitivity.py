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
    LEGACY_OUTPUT_DIR,
    candidate_roi_csv_paths,
    candidate_run_csv_paths,
    ensure_output_dirs,
    first_existing,
    legacy_combined_csv_path,
    tornado_csv_path,
)
from src.io_utils import STRUCTURAL_COLUMNS


def _pick_center(values):
    vals = sorted(pd.Series(values).dropna().unique().tolist())
    if not vals:
        return None
    return vals[len(vals) // 2]


def _infer_baseline_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Fallback baseline inference when is_baseline flag is missing/empty.

    Uses center-point prior values (middle mu, middle sigma, preferred dist) per targets group.
    """
    if df.empty:
        return df.copy()

    required = {"targets", "roi_prior_mu", "roi_prior_sigma", "roi_prior_dist"}
    if not required.issubset(df.columns):
        return df.iloc[0:0].copy()

    picked = []
    for t, g in df.groupby("targets", dropna=False):
        mu0 = _pick_center(g["roi_prior_mu"])
        sigma0 = _pick_center(g["roi_prior_sigma"])
        dists = [str(x) for x in g["roi_prior_dist"].dropna().unique().tolist()]
        dist0 = "Normal" if "Normal" in dists else (_pick_center(dists) if dists else None)

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


def _paths_for_tag(tag: str) -> dict[str, Path | list[Path]]:
    return {
        "run_csv_candidates": candidate_run_csv_paths(tag),
        "roi_csv_candidates": candidate_roi_csv_paths(tag),
        "legacy_csv": legacy_combined_csv_path(tag, LEGACY_OUTPUT_DIR),
        "tornado_csv": tornado_csv_path(tag, TABLES_DIR),
    }


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
    return parser


def _load_channel_spend(project_root: str, channels: list[str]) -> pd.DataFrame:
    data_csv = os.path.join(project_root, "data", "raw", "monthly_mocha.csv")
    raw_df = pd.read_csv(data_csv)

    records = []
    for channel in channels:
        spend_col = f"{channel}_spend"
        if spend_col in raw_df.columns:
            spend_total = float(pd.to_numeric(raw_df[spend_col], errors="coerce").fillna(0).sum())
            records.append({"channel": channel, "channel_total_spend": spend_total})

    return pd.DataFrame(records)


def _load_current_results(paths: dict[str, Path | list[Path]]) -> pd.DataFrame:
    run_candidates = paths["run_csv_candidates"]
    roi_candidates = paths["roi_csv_candidates"]

    run_csv = None
    roi_csv = None
    if run_candidates[0].exists() and roi_candidates[0].exists():
        run_csv = run_candidates[0]
        roi_csv = roi_candidates[0]
    elif run_candidates[1].exists() and roi_candidates[1].exists():
        run_csv = run_candidates[1]
        roi_csv = roi_candidates[1]
    else:
        run_csv = first_existing(run_candidates)
        roi_csv = first_existing(roi_candidates)

    if run_csv is not None and roi_csv is not None:
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
                *STRUCTURAL_COLUMNS,
                "is_baseline",
                "qc_status_code",
                "qc_summary_short",
                "qc_primary_review_check",
                "qc_flagged_channels",
            ] if c in run_df.columns
        ]
        run_meta = run_df[run_cols].drop_duplicates(subset=["run_id"]).copy()
        return roi_df.merge(run_meta, on="run_id", how="left", suffixes=("", "_run"))

    legacy_csv = paths["legacy_csv"]
    if legacy_csv.exists():
        return pd.read_csv(legacy_csv)

    return pd.DataFrame()


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
    tag = "_".join(targets_sorted)

    paths = _paths_for_tag(tag)
    out_csv = paths["tornado_csv"]
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    df = _load_current_results(paths)

    # Auto-run src.main --targets ... if results missing
    if df.empty:
        cmd = [sys.executable, "-m", "src.main", "--targets"] + targets_sorted

        print("Sensitivity outputs missing; generating them first via:")
        print(" ".join(cmd))

        proc = subprocess.run(cmd, cwd=project_root)
        if proc.returncode != 0:
            raise RuntimeError(f"Auto-run of src.main failed with exit code {proc.returncode}")

        df = _load_current_results(paths)
        if df.empty:
            run_candidates = ", ".join(str(p) for p in paths["run_csv_candidates"])
            roi_candidates = ", ".join(str(p) for p in paths["roi_csv_candidates"])
            raise FileNotFoundError(
                "Expected split outputs (or legacy combined output) still not found after auto-run: "
                f"{run_candidates} / {roi_candidates}"
            )

    # Summarize
    # Match targets string inside file
    targets_str = ",".join(targets_sorted)
    if "targets" not in df.columns:
        raise ValueError("Input CSV has no 'targets' column; cannot summarize multi-prior results.")
    df = df[df["targets"] == targets_str].copy()

    if "is_baseline" not in df.columns:
        raise ValueError("Missing column 'is_baseline' in results CSV. Cannot identify baseline reliably.")

    baseline_df = df[df["is_baseline"] == True].copy()
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
    baseline_summary = (
        baseline_df.groupby(["targets", "channel"])["estimated_roi"]
        .mean()
        .reset_index()
        .rename(columns={"estimated_roi": "roi_baseline"})
    )

    df = df.merge(baseline_summary, on=["targets", "channel"], how="left")
    df["roi_new"] = df["estimated_roi"]
    df["delta_abs"] = (df["roi_new"] - df["roi_baseline"]).abs()
    df["delta_pct"] = np.where(
        df["roi_baseline"] != 0,
        ((df["roi_new"] / df["roi_baseline"]) - 1).abs(),
        np.nan
    )

    spend_df = _load_channel_spend(project_root, sorted(df["channel"].dropna().astype(str).unique().tolist()))
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
        df = df[df["is_baseline"] == False].copy()
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
    print("Saved tornado-ready summary to:")
    print(out_csv)


if __name__ == "__main__":
    main()
