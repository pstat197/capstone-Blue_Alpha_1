# src/summarize_sensitivity.py
import os
import sys
import subprocess
import pandas as pd
import numpy as np

def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.join(project_root, "data", "output")
    os.makedirs(output_dir, exist_ok=True)

    # Positional targets only:
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    if len(argv) < 2:
        raise ValueError(
            "Usage:\n"
            "  python -m src.summarize_sensitivity <target1> <target2> [target3 ...]\n"
            "Example:\n"
            "  python -m src.summarize_sensitivity meta google"
        )

    targets = argv
    targets_sorted = sorted([str(t) for t in targets])
    tag = "_".join(targets_sorted)

    in_csv = os.path.join(output_dir, f"prior_sensitivity_results_multi_{tag}.csv")
    out_csv = os.path.join(output_dir, f"tornado_{tag}.csv")

    # Auto-run src.main --targets ... if results missing
    if not os.path.exists(in_csv):
        cmd = [sys.executable, "-m", "src.main", "--targets"] + targets_sorted

        print("Results CSV missing; generating it first via:")
        print(" ".join(cmd))

        proc = subprocess.run(cmd, cwd=project_root)
        if proc.returncode != 0:
            raise RuntimeError(f"Auto-run of src.main failed with exit code {proc.returncode}")

        if not os.path.exists(in_csv):
            raise FileNotFoundError(f"Expected results CSV still not found after auto-run: {in_csv}")

    # Summarize
    df = pd.read_csv(in_csv)

    # Match targets string inside file
    targets_str = ",".join(targets_sorted)
    if "targets" not in df.columns:
        raise ValueError("Input CSV has no 'targets' column; cannot summarize multi-prior results.")
    df = df[df["targets"] == targets_str].copy()

    if "is_baseline" not in df.columns:
        raise ValueError("Missing column 'is_baseline' in results CSV. Cannot identify baseline reliably.")

    baseline_df = df[df["is_baseline"] == True].copy()
    if baseline_df.empty:
        raise ValueError("No baseline rows found (is_baseline==True). Check baseline settings in main.py.")

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

    # remove baseline rows
    df = df[df["is_baseline"] == False].copy()

    required_cols = ["targets", "prior_key", "channel", "roi_baseline", "roi_new", "delta_abs", "delta_pct"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in results CSV: {missing}")

    df[required_cols].to_csv(out_csv, index=False)
    print("Saved tornado-ready summary to:")
    print(out_csv)

if __name__ == "__main__":
    main()