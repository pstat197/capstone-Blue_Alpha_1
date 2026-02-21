# src/main.py
import os
import json
import sys
import time
import subprocess

import pandas as pd
from src.experiment import build_experiment_config
from src.io_utils import normalize_columns, parse_channels_and_output

def main():
    channels = ["meta", "google", "snapchat", "tiktok", "moloco", "liveintent", "beehiiv", "amazon"]
    multipliers = [0.4, 0.7, 1.0, 1.4, 2.0]

    cfg = build_experiment_config(
        channels=channels,
        multipliers=multipliers,
        kpi_col="subscriptions",
        output_file="prior_sensitivity_results.csv",
    )

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_csv = os.path.join(project_root, "data", "raw", "monthly_mocha.csv")
    output_dir = os.path.join(project_root, "data", "output")
    os.makedirs(output_dir, exist_ok=True)

    target_channels_to_run, output_file = parse_channels_and_output(
        full_channels=channels,
        output_dir=output_dir,
        default_target="tiktok",
    )

    print("Spend cols used:", cfg.spend_cols)
    print("Computed mu0 =", round(cfg.mu0, 6))
    print("Mu grid =", cfg.roi_mu_values)
    print("Target channels to run:", target_channels_to_run)
    print("Output file:", output_file)

    channels_json = json.dumps(channels)

    # resume-safe
    if os.path.exists(output_file):
        results_df = pd.read_csv(output_file)
        print("Existing results found. Loading...")

        results_df = normalize_columns(results_df)

        # normalize float formatting to avoid float mismatch
        results_df["roi_prior_mu"] = pd.to_numeric(results_df["roi_prior_mu"], errors="coerce").round(6)
        results_df["roi_prior_sigma"] = pd.to_numeric(results_df["roi_prior_sigma"], errors="coerce").round(6)
        results_df["roi_prior_dist"] = results_df["roi_prior_dist"].astype(str)

        already_done = set(
            zip(
                results_df["target_channel"].astype(str),
                results_df["roi_prior_mu"],
                results_df["roi_prior_sigma"],
                results_df["roi_prior_dist"],
            )
        )
    else:
        already_done = set()

    total_runs = len(target_channels_to_run) * len(cfg.roi_mu_values) * len(cfg.roi_sigma_values) * len(cfg.roi_dist_values)
    run_id = 1

    for target_channel in target_channels_to_run:
        for mu in cfg.roi_mu_values:
            sigma_values = cfg.roi_sigma_values
            dist_values = cfg.roi_dist_values

            for sigma in sigma_values:
                for dist in dist_values:
                    # round mu consistently
                    mu = round(float(mu), 6)
                    sigma = round(float(sigma), 6)
                    dist = str(dist)

                    if (target_channel, mu, sigma, dist) in already_done:
                        print(f"Skipping {target_channel}, mu={mu}, sigma={sigma}, dist={dist}")
                        run_id += 1
                        continue

                    print(f"\n===== Run {run_id}/{total_runs} =====")
                    print(f"Channel: {target_channel}, Prior mu: {mu}, Prior sigma: {sigma}, Dist: {dist}")

                    t0 = time.time()
                    mu_tag = str(mu).replace(".", "p")
                    sigma_tag = str(sigma).replace(".", "p")
                    dist_tag = dist
                    tmp_out = os.path.join(output_dir, f"_tmp_roi_{target_channel}_{mu_tag}_{sigma_tag}_{dist_tag}.csv")

                    cmd = [
                        sys.executable, "-m", "src.run_meridian_once",
                        "--csv", data_csv,
                        "--channels_json", channels_json,
                        "--target_channel", target_channel,
                        "--mu", str(mu),
                        "--sigma", str(sigma),
                        "--dist", dist,
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

                    if proc.returncode != 0:
                        print("\n--- Subprocess STDOUT ---\n", proc.stdout)
                        print("\n--- Subprocess STDERR ---\n", proc.stderr)
                        raise RuntimeError(f"Subprocess failed with code {proc.returncode}")

                    stderr_lines = proc.stderr.splitlines()
                    useful = [
                        ln for ln in stderr_lines
                        if not ln.startswith("WARNING:") and not ln.startswith("WARNING:tensorflow:")
                    ]

                    useful = [ln for ln in useful if "device_compiler.h" not in ln and "Compiled cluster using XLA" not in ln]

                    if useful:
                        print("\n--- Subprocess STDERR (filtered) ---\n", "\n".join(useful))

                    if not os.path.exists(tmp_out):
                        raise FileNotFoundError(f"Subprocess finished but output missing: {tmp_out}")

                    part = pd.read_csv(tmp_out)

                    # normalize tmp output schema too (in case it's old column names)
                    part = normalize_columns(part)

                    part["roi_prior_mu"] = pd.to_numeric(part["roi_prior_mu"], errors="coerce").round(6)
                    part["roi_prior_sigma"] = pd.to_numeric(part["roi_prior_sigma"], errors="coerce").round(6)
                    part["roi_prior_dist"] = part["roi_prior_dist"].astype(str)

                    write_header = (not os.path.exists(output_file)) or (os.path.getsize(output_file) == 0)
                    part.to_csv(output_file, mode="a", header=write_header, index=False)
                    already_done.add((target_channel, mu, sigma, dist))

                    os.remove(tmp_out)

                    print("Iteration time:", round(time.time() - t0, 2), "seconds")
                    run_id += 1

    print("\nALL RUNS COMPLETED.")
    print("Saved to:", output_file)


if __name__ == "__main__":
    main()