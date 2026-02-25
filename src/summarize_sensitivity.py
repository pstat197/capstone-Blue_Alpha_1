import os
import pandas as pd
import numpy as np


def build_prior_key(row, baseline_mu):

    if baseline_mu == 0:
        return "mu_xNA"
    
    multiplier = round(row["roi_prior_mu"] / baseline_mu, 3)
    return f"mu_x{multiplier}"

def main():

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    output_dir = os.path.join(project_root, "data", "output")
    os.makedirs(output_dir, exist_ok=True)

    data_csv = os.path.join(project_root, "data", "output", "prior_sensitivity_results_multi_meta_tiktok.csv")
    output_file = os.path.join(project_root, "data", "output", "prior_sensitivity_summary_tiktok_meta.csv")

    df = pd.read_csv(data_csv)

    final_rows = []

    baseline_mask = (
        (df["roi_prior_mu"] == df["roi_prior_mu"].median()) &
        (df["roi_prior_dist"] == "LogNormal")
    )

    baseline_df = df[baseline_mask]

    if baseline_df.empty:
        print("No baseline found.")
        return
    
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
        None
    )

    df = df[~df["is_baseline"]]

    result = df[[
        "targets",
        "prior_key",
        "channel",
        "roi_baseline",
        "roi_new",
        "delta_abs",
        "delta_pct"
    ]]

    result.to_csv(output_file, index=False)

    print("Saved tornado-ready summary to:")
    print(output_file)

if __name__ == "__main__":
    main()