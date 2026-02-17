# src/main.py
import os
import json
import sys
import time
import subprocess
print("MAIN sys.executable =", sys.executable)

import pandas as pd
from psutil import virtual_memory

def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_csv = os.path.join(project_root, "data", "raw", "monthly_mocha.csv")
    src_dir = os.path.join(project_root, "src")          
    output_dir = os.path.join(project_root, "data", "output")
    os.makedirs(output_dir, exist_ok=True)

    output_file = os.path.join(output_dir, "prior_sensitivity_results.csv")

    channels = ["meta","google","snapchat","tiktok","moloco", "liveintent", "beehiiv", "amazon"]
    roi_mu_values = [0.2, 0.4, 0.6, 0.8]

    channels_json = json.dumps(channels)

    # resume-safe
    if os.path.exists(output_file):
        results_df = pd.read_csv(output_file)
        print("Existing results found. Loading...")
    else:
        results_df = pd.DataFrame(columns=["channel","estimated_roi","target_channel","roi_prior_mu"])

    already_done = set()
    if len(results_df):
        already_done = set(zip(results_df["target_channel"], results_df["roi_prior_mu"]))

    total_runs = len(channels) * len(roi_mu_values)
    run_id = 1

    for target_channel in channels:
        for mu in roi_mu_values:

            if (target_channel, mu) in already_done:
                print(f"Skipping {target_channel}, mu={mu}")
                run_id += 1
                continue

            print(f"\n===== Run {run_id}/{total_runs} =====")
            print(f"Channel: {target_channel}, Prior mu: {mu}")
            print("RAM before run:", virtual_memory().percent, "%")

            t0 = time.time()
            tmp_out = os.path.join(output_dir, f"_tmp_roi_{target_channel}_{mu}.csv")

            print("RAM after run:", virtual_memory().percent, "%")
            cmd = [
                sys.executable, "run_meridian_once.py",
                "--csv", data_csv,
                "--channels_json", channels_json,
                "--target_channel", target_channel,
                "--mu", str(mu),
                "--out_csv", tmp_out,
                "--n_chains", "1",
                "--n_adapt", "100",
                "--n_burnin", "50",
                "--n_keep", "20",
                "--seed", "0",
            ]

            # run subprocess from src/ so "from utils import ..." works
            proc = subprocess.run(
                cmd,
                cwd=src_dir,
                capture_output=True,
                text=True
            )

            print("\n--- Subprocess STDOUT ---\n", proc.stdout)
            print("\n--- Subprocess STDERR ---\n", proc.stderr)

            if proc.returncode != 0:
                raise RuntimeError(f"Subprocess failed with code {proc.returncode}")

            if not os.path.exists(tmp_out):
                raise FileNotFoundError(f"Subprocess finished but output missing: {tmp_out}")

            part = pd.read_csv(tmp_out)
            results_df = pd.concat([results_df, part], ignore_index=True)
            results_df.to_csv(output_file, index=False)

            os.remove(tmp_out)

            print("RAM after run (parent):", virtual_memory().percent, "%")
            print("Iteration time:", round(time.time() - t0, 2), "seconds")

            run_id += 1

    print("\nALL RUNS COMPLETED.")
    print("Saved to:", output_file)

if __name__ == "__main__":
    main()
