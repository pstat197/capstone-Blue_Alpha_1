# src/main.py
import os
import json
import sys
import time
import subprocess

from src.experiment import build_experiment_config
from src.io_utils import (
    parse_channels_and_output,
    load_resume_state,
    append_tmp_to_output,
    RUN_OUTPUT_COLUMNS,
    ROI_OUTPUT_COLUMNS,
)


def build_run_id(scope: str, mu: float, sigma: float, dist: str) -> str:
    return f"{scope}|{float(mu):.6f}|{float(sigma):.6f}|{str(dist)}"

def main():
    channels = ["meta", "google", "snapchat", "tiktok", "moloco", "liveintent", "beehiiv", "amazon"]
    multipliers = [0.4, 1.0, 2.0]

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

    target_channels_to_run, output_file, targets = parse_channels_and_output(
        full_channels=channels,
        output_dir=output_dir,
        default_target="tiktok",
    )
    run_output_file = output_file.replace("prior_sensitivity_results", "prior_sensitivity_runs", 1)
    roi_output_file = output_file.replace("prior_sensitivity_results", "prior_sensitivity_roi", 1)

    channels_json = json.dumps(channels)

    print("Spend cols used:", cfg.spend_cols)
    print("Computed mu0 =", round(cfg.mu0, 6))
    print("Mu grid =", cfg.roi_mu_values)
    print("Run output file:", run_output_file)
    print("ROI output file:", roi_output_file)

    baseline_mu = cfg.mu0
    baseline_sigma = cfg.roi_sigma_values[1]
    baseline_dist = cfg.roi_dist_values[0]
    
    # resume-safe load
    already_done = load_resume_state(run_output_file)

    env = os.environ.copy()
    env["TF_CPP_MIN_LOG_LEVEL"] = "3"
    env["TF_ENABLE_ONEDNN_OPTS"] = "0"

    # MODE A: multiprior (linked)
    if targets is not None:
        targets = sorted([str(x) for x in targets])
        targets_str = ",".join(targets)
        targets_tag = "_".join(targets)

        print("MODE: MULTI-PRIOR (linked)")
        print("Targets to perturb together:", targets_str)

        total_runs = len(cfg.roi_mu_values) * len(cfg.roi_sigma_values) * len(cfg.roi_dist_values)
        run_index = 1

        for mu in cfg.roi_mu_values:
            for sigma in cfg.roi_sigma_values:
                for dist in cfg.roi_dist_values:
                    
                    mu = round(float(mu), 6)
                    sigma = round(float(sigma), 6)
                    dist = str(dist)

                    overrides = {ch: {"mu": mu, "sigma": sigma, "dist": dist} for ch in targets}
                    prior_key = json.dumps(overrides, sort_keys=True)
                    run_key = build_run_id(f"multi|{targets_str}", mu, sigma, dist)

                    if run_key in already_done:
                        print(f"Skipping targets={targets_str}, mu={mu}, sigma={sigma}, dist={dist}")
                        run_index += 1
                        continue

                    print(f"\n===== Run {run_index}/{total_runs} =====")
                    print(f"Targets: {targets_str}, Prior mu: {mu}, Prior sigma: {sigma}, Dist: {dist}")

                    t0 = time.time()
                    mu_tag = str(mu).replace(".", "p")
                    sigma_tag = str(sigma).replace(".", "p")
                    dist_tag = dist
                    tmp_run_out = os.path.join(output_dir, f"_tmp_run_{targets_tag}_{mu_tag}_{sigma_tag}_{dist_tag}.csv")
                    tmp_roi_out = os.path.join(output_dir, f"_tmp_roi_{targets_tag}_{mu_tag}_{sigma_tag}_{dist_tag}.csv")

                    cmd = [
                        sys.executable, "-m", "src.run_meridian_once",
                        "--csv", data_csv,
                        "--channels_json", channels_json,
                        "--roi_prior_overrides_json", prior_key,
                        "--out_run_csv", tmp_run_out,
                        "--out_roi_csv", tmp_roi_out,
                        "--baseline_mu", str(baseline_mu),
                        "--baseline_sigma", str(baseline_sigma),
                        "--baseline_dist", str(baseline_dist),
                        "--n_chains", "2",
                        "--n_adapt", "300",
                        "--n_burnin", "300",
                        "--n_keep", "100",
                        "--seed", "0",
                    ]

                    proc = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, env=env)
                    if proc.returncode != 0:
                        print("\n--- Subprocess STDOUT ---\n", proc.stdout)
                        print("\n--- Subprocess STDERR ---\n", proc.stderr)
                        raise RuntimeError(f"Subprocess failed with code {proc.returncode}")

                    append_tmp_to_output(
                        tmp_out=tmp_run_out,
                        output_file=run_output_file,
                        ensure_cols={
                            "run_id": run_key,
                            "prior_key": prior_key,
                            "targets": targets_str,
                            "target_channel": targets_str,
                        },
                        expected_columns=RUN_OUTPUT_COLUMNS,
                        cast_single_target=False,
                        normalize_part=True,
                    )
                    append_tmp_to_output(
                        tmp_out=tmp_roi_out,
                        output_file=roi_output_file,
                        ensure_cols={
                            "run_id": run_key,
                            "prior_key": prior_key,
                        },
                        expected_columns=ROI_OUTPUT_COLUMNS,
                        cast_single_target=False,
                        normalize_part=False,
                    )

                    already_done.add(run_key)
                    os.remove(tmp_run_out)
                    os.remove(tmp_roi_out)

                    print("Iteration time:", round(time.time() - t0, 2), "seconds")
                    run_index += 1

        print("\nALL RUNS COMPLETED.")
        print("Saved run diagnostics to:", run_output_file)
        print("Saved ROI results to:", roi_output_file)
        return

    # MODE B: single-target
    print("MODE: SINGLE-TARGET")
    print("Target channels to run:", target_channels_to_run)

    total_runs = len(target_channels_to_run) * len(cfg.roi_mu_values) * len(cfg.roi_sigma_values) * len(cfg.roi_dist_values)
    run_index = 1

    for target_channel in target_channels_to_run:
        for mu in cfg.roi_mu_values:
            for sigma in cfg.roi_sigma_values:
                for dist in cfg.roi_dist_values:
                    mu = round(float(mu), 6)
                    sigma = round(float(sigma), 6)
                    dist = str(dist)
                    run_key = build_run_id(f"single|{target_channel}", mu, sigma, dist)

                    if run_key in already_done:
                        print(f"Skipping {target_channel}, mu={mu}, sigma={sigma}, dist={dist}")
                        run_index += 1
                        continue

                    print(f"\n===== Run {run_index}/{total_runs} =====")
                    print(f"Channel: {target_channel}, Prior mu: {mu}, Prior sigma: {sigma}, Dist: {dist}")

                    t0 = time.time()
                    mu_tag = str(mu).replace(".", "p")
                    sigma_tag = str(sigma).replace(".", "p")
                    dist_tag = dist
                    tmp_run_out = os.path.join(output_dir, f"_tmp_run_{target_channel}_{mu_tag}_{sigma_tag}_{dist_tag}.csv")
                    tmp_roi_out = os.path.join(output_dir, f"_tmp_roi_{target_channel}_{mu_tag}_{sigma_tag}_{dist_tag}.csv")
                    


                    cmd = [
                        sys.executable, "-m", "src.run_meridian_once",
                        "--csv", data_csv,
                        "--channels_json", channels_json,
                        "--target_channel", target_channel,
                        "--mu", str(mu),
                        "--sigma", str(sigma),
                        "--dist", dist,
                        "--out_run_csv", tmp_run_out,
                        "--out_roi_csv", tmp_roi_out,
                        "--baseline_mu", str(baseline_mu),
                        "--baseline_sigma", str(baseline_sigma),
                        "--baseline_dist", baseline_dist,
                        "--n_chains", "1",
                        "--n_adapt", "100",
                        "--n_burnin", "50",
                        "--n_keep", "20",
                        "--seed", "0",
                    ]

                    proc = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, env=env)
                    if proc.returncode != 0:
                        print("\n--- Subprocess STDOUT ---\n", proc.stdout)
                        print("\n--- Subprocess STDERR ---\n", proc.stderr)
                        raise RuntimeError(f"Subprocess failed with code {proc.returncode}")

                    append_tmp_to_output(
                        tmp_out=tmp_run_out,
                        output_file=run_output_file,
                        ensure_cols={"run_id": run_key},
                        cast_single_target=True,
                        expected_columns=RUN_OUTPUT_COLUMNS,
                        normalize_part=True,
                    )
                    append_tmp_to_output(
                        tmp_out=tmp_roi_out,
                        output_file=roi_output_file,
                        ensure_cols={"run_id": run_key},
                        cast_single_target=False,
                        expected_columns=ROI_OUTPUT_COLUMNS,
                        normalize_part=False,
                    )

                    already_done.add(run_key)
                    os.remove(tmp_run_out)
                    os.remove(tmp_roi_out)

                    print("Iteration time:", round(time.time() - t0, 2), "seconds")
                    run_index += 1

    print("\nALL RUNS COMPLETED.")
    print("Saved run diagnostics to:", run_output_file)
    print("Saved ROI results to:", roi_output_file)


if __name__ == "__main__":
    main()
