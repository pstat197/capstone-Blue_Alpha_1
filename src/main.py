# src/main.py
import os
import json
import sys
import time
import subprocess

from src.experiment import build_experiment_config
from src.run_config import load_run_config
from src.io_utils import (
    parse_channels_and_output,
    load_resume_state,
    append_tmp_to_output,
    RUN_OUTPUT_COLUMNS,
    ROI_OUTPUT_COLUMNS,
)


def build_run_id(scope: str, mu: float, sigma: float, dist: str) -> str:
    return f"{scope}|{float(mu):.6f}|{float(sigma):.6f}|{str(dist)}"


def _extract_config_path(argv: list[str]) -> str | None:
    for i, token in enumerate(argv):
        if token == "--config" and i + 1 < len(argv):
            return argv[i + 1]
        if token.startswith("--config="):
            return token.split("=", 1)[1]
    return None


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = _extract_config_path(sys.argv[1:])
    if config_path and not os.path.isabs(config_path):
        config_path = os.path.join(project_root, config_path)
    run_cfg = load_run_config(config_path)

    channels = [str(x) for x in run_cfg["model"]["channels"]]
    multipliers = [float(x) for x in run_cfg["experiment"]["multipliers"]]
    mu_grid = run_cfg["experiment"].get("roi_mu_values")
    if mu_grid is not None:
        mu_grid = [float(x) for x in mu_grid]
    sigma_grid = run_cfg["experiment"].get("roi_sigma_values")
    if sigma_grid is not None:
        sigma_grid = [float(x) for x in sigma_grid]
    dist_grid = [str(x) for x in run_cfg["experiment"].get("roi_dist_values", ["Normal", "LogNormal"])]
    kpi_col = str(run_cfg["model"].get("kpi_col", "subscriptions"))
    default_targets = [str(x) for x in run_cfg.get("defaults", {}).get("targets", ["tiktok"])]

    cfg = build_experiment_config(
        channels=channels,
        multipliers=multipliers,
        kpi_col=kpi_col,
        mu_grid=mu_grid,
        sigma_grid=sigma_grid,
        dist_grid=dist_grid,
        output_file="prior_sensitivity_results.csv",
    )

    data_csv = os.path.join(project_root, "data", "raw", "monthly_mocha.csv")
    output_dir = os.path.join(project_root, "data", "output")
    os.makedirs(output_dir, exist_ok=True)

    _, output_file, targets = parse_channels_and_output(
        full_channels=channels,
        output_dir=output_dir,
        default_target=default_targets,
    )
    if targets is None or len(targets) == 0:
        raise ValueError("No targets provided. Pass --targets <channel...> or --channels <channel...>.")

    run_output_file = output_file.replace("prior_sensitivity_results", "prior_sensitivity_runs", 1)
    roi_output_file = output_file.replace("prior_sensitivity_results", "prior_sensitivity_roi", 1)

    channels_json = json.dumps(channels)

    print("Spend cols used:", cfg.spend_cols)
    print("Computed mu0 =", round(cfg.mu0, 6))
    print("Mu grid =", cfg.roi_mu_values)
    print("Sigma grid =", cfg.roi_sigma_values)
    print("Dist grid =", cfg.roi_dist_values)
    print("Run output file:", run_output_file)
    print("ROI output file:", roi_output_file)

    baseline_mu = cfg.mu0
    baseline_sigma = cfg.roi_sigma_values[min(1, len(cfg.roi_sigma_values) - 1)]
    baseline_dist = cfg.roi_dist_values[0]
    
    # resume-safe load
    already_done = load_resume_state(run_output_file)

    env = os.environ.copy()
    env["TF_CPP_MIN_LOG_LEVEL"] = "3"
    env["TF_ENABLE_ONEDNN_OPTS"] = "0"

    targets = sorted([str(x) for x in targets])
    targets_str = ",".join(targets)
    targets_tag = "_".join(targets)

    print("MODE: LINKED TARGET-SET (UNIFIED)")
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
                    "--n_chains", str(int(sampler["n_chains"])),
                    "--n_adapt", str(int(sampler["n_adapt"])),
                    "--n_burnin", str(int(sampler["n_burnin"])),
                    "--n_keep", str(int(sampler["n_keep"])),
                    "--seed", str(int(sampler["seed"])),
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


if __name__ == "__main__":
    main()
    sampler = run_cfg["sampler"]
