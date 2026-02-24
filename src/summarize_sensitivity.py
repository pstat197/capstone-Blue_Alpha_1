import os
import pandas as pd


def build_prior_key(row, baseline_mu):
    multiplier = round(row["roi_prior_mu"] / baseline_mu, 3)

    return f"mu_x{multiplier}_sigma{row['roi_prior_sigma']}_dist{row['roi_prior_dist']}"

def main():

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    output_dir = os.path.join(project_root, "data", "output")
    os.makedirs(output_dir, exist_ok=True)

    data_csv = os.path.join(project_root, "data", "output", "prior_sensitivity_results_tiktok_meta.csv")
    output_file = os.path.join(project_root, "data", "output", "prior_sensitivity_summary_tiktok_meta.csv")

    pair_name = "tiktok_meta"

    df = pd.read_csv(data_csv)

    final_rows = []

    for channel in df["target_channel"].unique():
        channel_df = df[df["target_channel"] == channel]

        channel_df = channel_df[channel_df["channel"] == channel]

        if channel_df.empty:
            print(f"No data for channel {channel}, skipping...")
            continue



        baseline_row = channel_df[channel_df["is_baseline"] == True]

        if baseline_row.empty:
            print(f"No baseline found for channel {channel}, skipping...")
            continue
        elif len(baseline_row) != 1:
            print(f"Multiple baselines found for channel {channel}, found {len(baseline_row)}, skipping...")
            continue

        baseline_roi = baseline_row["estimated_roi"].iloc[0]
        baseline_mu = baseline_row["roi_prior_mu"].iloc[0]

        channel_df["roi_baseline"] = baseline_roi
        channel_df["roi_new"] = channel_df["estimated_roi"]
        channel_df["delta_abs"] = (channel_df["roi_new"] - baseline_roi).abs()

        if baseline_roi != 0:
            channel_df["delta_pct"] = ((channel_df["roi_new"] / baseline_roi) - 1).abs()
        else:
            channel_df["delta_pct"] = None
        
        channel_df["prior_key"] = channel_df.apply(lambda row: build_prior_key(row, baseline_mu), axis=1)

        channel_df["targets"] = pair_name

        final_rows.append(
            channel_df[[
                "targets",
                "prior_key",
                "channel",
                "roi_baseline",
                "roi_new",
                "delta_abs",
                "delta_pct"
            ]]
        )
    
    if not final_rows:
        print("No data processed.")
        return
    
    result = pd.concat(final_rows, ignore_index=True)

    result = result[result["delta_abs"] > 0]

    result.to_csv(output_file, index=False)

    print("\nTornado ready files saved to:")
    print(output_file)

if __name__ == "__main__":
    main()