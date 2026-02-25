import os
import pandas as pd
import numpy as np

from src.io_utils import parse_targets_and_tornado_paths


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.join(project_root, "data", "output")
    os.makedirs(output_dir, exist_ok=True)

    # pick input/output based on --targets or --channels
    in_csv, out_csv, targets = parse_targets_and_tornado_paths(output_dir=output_dir)

    if not os.path.exists(in_csv):
        raise FileNotFoundError(
            f"Results CSV not found: {in_csv}\n"
            "Run `python -m src.main --targets ...` (or --channels ...) first."
        )

    df = pd.read_csv(in_csv)

    if targets is not None:
        targets_str = ",".join(sorted([str(t) for t in targets]))
        if "targets" not in df.columns:
            raise ValueError("Input CSV has no 'targets' column; cannot summarize multi-prior targets.")
        df = df[df["targets"] == targets_str].copy()

    # baseline selection
    if "is_baseline" not in df.columns:
        raise ValueError("Missing column 'is_baseline' in results CSV. Cannot identify baseline reliably.")

    baseline_df = df[df["is_baseline"] == True].copy()
    if baseline_df.empty:
        raise ValueError("No baseline rows found (is_baseline==True). Check baseline settings in main.py.")

    group_keys = ["channel"]
    if "targets" in df.columns:
        group_keys = ["targets", "channel"]

    baseline_summary = (
        baseline_df.groupby(group_keys)["estimated_roi"]
        .mean()
        .reset_index()
        .rename(columns={"estimated_roi": "roi_baseline"})
    )

    df = df.merge(baseline_summary, on=group_keys, how="left")

    df["roi_new"] = df["estimated_roi"]
    df["delta_abs"] = (df["roi_new"] - df["roi_baseline"]).abs()
    df["delta_pct"] = np.where(
        df["roi_baseline"] != 0,
        ((df["roi_new"] / df["roi_baseline"]) - 1).abs(),
        np.nan
    )

    # remove baseline rows
    df = df[df["is_baseline"] == False].copy()

    required_cols = ["targets", "prior_key", "channel", "roi_baseline", "roi_new", "delta_abs", "delta_pct"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in results CSV: {missing}")

    result = df[required_cols].copy()
    result.to_csv(out_csv, index=False)

    print("Saved tornado-ready summary to:")
    print(out_csv)

if __name__ == "__main__":
    main()