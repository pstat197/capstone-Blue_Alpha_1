# src/main.py
import os
import json
import sys
import time
import subprocess

import pandas as pd
from src.experiment import build_experiment_config

def main():
    channels = ["meta","google","snapchat","tiktok","moloco", "liveintent", "beehiiv", "amazon"]
    multipliers = [0.4, 0.7, 1.0, 1.4, 2.0]

    cfg = build_experiment_config(
        channels=channels,
        multipliers=multipliers,
        kpi_col="subscriptions", 
    )

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_csv = os.path.join(project_root, "data", "raw", "monthly_mocha.csv")
    output_dir = os.path.join(project_root, "data", "output")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "prior_sensitivity_results_5mu.csv")
    
    print("Spend cols used:", cfg.spend_cols)
    print("Computed mu0 =", round(cfg.mu0, 6))
    print("Mu grid =", cfg.roi_mu_values)

    channels_json = json.dumps(channels)

    # resume-safe
    if os.path.exists(output_file):
        results_df = pd.read_csv(output_file)
        print("Existing results found. Loading...")
        # normalize float formatting to avoid float mismatch
        results_df["roi_prior_mu"] = results_df["roi_prior_mu"].astype(float).round(6)
        already_done = set(zip(results_df["target_channel"].astype(str), results_df["roi_prior_mu"]))
    else:
        already_done = set()

    total_runs = len(cfg.channels) * len(cfg.roi_mu_values)
    run_id = 1

    for target_channel in channels:
        for mu in cfg.roi_mu_values:
            # round mu consistently
            mu = round(float(mu), 6)

            if (target_channel, mu) in already_done:
                print(f"Skipping {target_channel}, mu={mu}")
                run_id += 1
                continue

            print(f"\n===== Run {run_id}/{total_runs} =====")
            print(f"Channel: {target_channel}, Prior mu: {mu}")

            t0 = time.time()
            mu_tag = str(mu).replace(".", "p")
            tmp_out = os.path.join(output_dir, f"_tmp_roi_{target_channel}_{mu_tag}.csv")
            
            cmd = [
                sys.executable, "-m", "src.run_meridian_once",
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

            env = os.environ.copy()
            env["TF_CPP_MIN_LOG_LEVEL"] = "3"   # suppress INFO/WARN
            env["TF_ENABLE_ONEDNN_OPTS"] = "0"

            proc = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, env=env)

            print("\n--- Subprocess STDOUT ---\n", proc.stdout)
            print("\n--- Subprocess STDERR ---\n", proc.stderr)

            if proc.returncode != 0:
                print("\n--- Subprocess STDOUT ---\n", proc.stdout)
                print("\n--- Subprocess STDERR ---\n", proc.stderr)
                raise RuntimeError(f"Subprocess failed with code {proc.returncode}")

            if not os.path.exists(tmp_out):
                raise FileNotFoundError(f"Subprocess finished but output missing: {tmp_out}")

            part = pd.read_csv(tmp_out)
            part["roi_prior_mu"] = part["roi_prior_mu"].astype(float).round(6)
            write_header = (not os.path.exists(output_file)) or (os.path.getsize(output_file) == 0)
            part.to_csv(output_file, mode="a", header=write_header, index=False) 
            already_done.add((target_channel, mu))         

            os.remove(tmp_out)

            print("Iteration time:", round(time.time() - t0, 2), "seconds")

            run_id += 1

    print("\nALL RUNS COMPLETED.")
    print("Saved to:", output_file)

if __name__ == "__main__":
    main()
