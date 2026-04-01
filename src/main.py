# src/main.py
from email import parser
import os
import json
import sys
import time
import subprocess
import argparse
import pandas as pd

from src.experiment import (
    build_experiment_config,
    detect_channels
)
from src.run_config import load_run_config
from src.io_utils import (
    parse_channels_and_output,
    load_resume_state,
    append_tmp_to_output,
    select_csv,
    RUN_OUTPUT_COLUMNS,
    ROI_OUTPUT_COLUMNS,
)
from src.output_paths import (
    RUNS_DIR,
    candidate_run_csv_paths,
    ensure_output_dirs,
    roi_csv_path,
    run_csv_path,
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
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ensure_output_dirs()

        parser = argparse.ArgumentParser()
        parser.add_argument("--config", type=str, default=None)
        parser.add_argument("--targets", nargs="+")
        parser.add_argument("--channels", nargs="+")  # keep alias
        parser.add_argument("--csv", type=str, default=None)

        args = parser.parse_args()

        config_path = args.config
        if config_path and not os.path.isabs(config_path):
            config_path = os.path.join(project_root, config_path)
        run_cfg = load_run_config(config_path)
        sampler = run_cfg["sampler"]

        csv_path = args.csv
        targets_input = args.targets or args.channels

        try:
            data_csv = select_csv(project_root, csv_path)
        except FileNotFoundError as e:
            print("\n===== ERROR OCCURRED =====")
            print(e)
            print("\nExample:")
            print("python -m src.main --targets your_target(s) --csv data/raw/your_data.csv")
            sys.exit(1)

        df = pd.read_csv(data_csv)

        revenue_col = [c for c in df.columns if c.lower() in ["revenue", "rev", "total_revenue"]]
        if revenue_col:
            kpi_col = revenue_col[0]
            print(f"Detected revenue column: '{kpi_col}'")
        else:
            while True:
                kpi_col = input("No revenue column detected. Please enter the KPI column name (e.g., 'subscriptions'): ").strip()
                if kpi_col in df.columns:
                    print(f"Using '{kpi_col}' as KPI column.")
                    break
                else:
                    print(f"Column '{kpi_col}' not found in data. Available columns: {list(df.columns)}")
        
        if kpi_col.lower() not in ["revenue", "rev", "total_revenue"]:
            while True:
                try:
                    multiplier_input = input("KPI column does not appear to be revenue. Please enter a multiplier to convert to revenue (e.g., 100 if 1 subscription ≈ $100 revenue): ").strip()
                    multiplier = float(multiplier_input)
                    break
                except ValueError:
                    print("Invalid input. Please enter a number to multiply the KPI by.")
            revenue_col = f"{kpi_col}_as_revenue"
            df[revenue_col] = df[kpi_col] * multiplier
            temp = data_csv.replace(".csv", "_with_revenue.csv") # overwrite with new revenue column
            df.to_csv(temp, index=False)
            data_csv = temp
            print(f"Created new revenue column '{revenue_col}' by multiplying '{kpi_col}' by {multiplier}.")
        else:
            revenue_col = kpi_col
            print(f"KPI '{kpi_col}' will be used directly as revenue. No conversion needed.")

        print("\n===== CHANNEL CONFIG =====")
        if args.csv:
            channels = detect_channels(df)
            print(f"Automatically detected channels from data: {channels}")
        else:
            channels = [str(x) for x in run_cfg["model"]["channels"]]
            print(f"Using channels from config: {channels}")
        if not channels:
            raise ValueError("No channels detected. Please ensure your CSV has columns ending with '_spend' or specify channels in the config.")

        default_multipliers = [float(x) for x in run_cfg["experiment"]["multipliers"]]
        
        print("\n===== GRID CONFIGURATION =====")
        mu_input = input(f"Enter mu multipliers separated by comma or press enter to use (default {default_multipliers}): ").strip()
        mu_mult = [float(x) for x in mu_input.split(",")] if mu_input else default_multipliers

        sigma_input = input(f"Enter sigma multipliers separated by comma or press enter to use (default {default_multipliers}): ").strip()
        sigma_mult = [float(x) for x in sigma_input.split(",")] if sigma_input else default_multipliers

        dist_input = input("Enter distribution types separated by comma (e.g., Normal,LogNormal) or press enter to use (default Normal,LogNormal): ").strip()
        dist_grid = [str(x).strip() for x in dist_input.split(",")] if dist_input else ["Normal", "LogNormal"]

        cfg = build_experiment_config(
            channels=channels,
            multipliers=default_multipliers,
            kpi_col=revenue_col,
            mu_grid=None,
            sigma_grid=None,
            dist_grid=dist_grid,
            output_file="prior_sensitivity_results.csv",
            data_csv=data_csv,
        )

        baseline_mu_input = input(f"Enter baseline prior mu (press Enter to use computed {cfg.mu0}): ").strip()
        baseline_mu = float(baseline_mu_input) if baseline_mu_input else cfg.mu0

        sigma0 = cfg.roi_sigma_values[min(1, len(cfg.roi_sigma_values) - 1)]
        baseline_sigma_input = input(f"Enter baseline prior sigma (press Enter to use computed {sigma0}): ").strip()
        baseline_sigma = float(baseline_sigma_input) if baseline_sigma_input else sigma0

        baseline_dist_input = input(f"Enter baseline prior distribution (press Enter to use computed {cfg.roi_dist_values[0]}): ").strip()
        baseline_dist = str(baseline_dist_input) if baseline_dist_input else cfg.roi_dist_values[0]

        print(f"\nUsing baseline_mu={baseline_mu}, baseline_sigma={baseline_sigma}, baseline_dist={baseline_dist}")

        mu_grid = [round(baseline_mu * m, 6) for m in mu_mult]
        sigma_grid = [round(baseline_sigma * m, 6) for m in sigma_mult]


        cfg.roi_mu_values = mu_grid
        cfg.roi_sigma_values = sigma_grid
        cfg.roi_dist_values = dist_grid

        output_dir = str(RUNS_DIR)
        os.makedirs(output_dir, exist_ok=True)

        _, _, targets, _ = parse_channels_and_output(
            full_channels=channels,
            output_dir=output_dir,
            default_target=targets_input if targets_input else ["google"],
        )
        if targets is None or len(targets) == 0:
            raise ValueError("No targets provided. Pass --targets <channel...> or --channels <channel...>.")

        targets = sorted([str(x) for x in targets])
        targets_tag = "_".join(targets)

        run_output_file = str(run_csv_path(targets_tag, RUNS_DIR))
        roi_output_file = str(roi_csv_path(targets_tag, RUNS_DIR))
        tmp_dir = os.path.dirname(run_output_file)
        os.makedirs(tmp_dir, exist_ok=True)

        channels_json = json.dumps(channels)

        print("Spend cols used:", cfg.spend_cols)
        print("Computed mu0 =", round(cfg.mu0, 6))
        print("Mu grid =", cfg.roi_mu_values)
        print("Sigma grid =", cfg.roi_sigma_values)
        print("Dist grid =", cfg.roi_dist_values)
        print("Run output file:", run_output_file)
        print("ROI output file:", roi_output_file)
        
        # resume-safe load
        already_done = load_resume_state(run_output_file)
        for legacy_path in candidate_run_csv_paths(targets_tag)[1:]:
            legacy_run_output_file = str(legacy_path)
            if legacy_run_output_file != run_output_file and os.path.exists(legacy_run_output_file):
                already_done.update(load_resume_state(legacy_run_output_file))

        env = os.environ.copy()
        env["TF_CPP_MIN_LOG_LEVEL"] = "3"
        env["TF_ENABLE_ONEDNN_OPTS"] = "0"

        targets_str = ",".join(targets)

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
                    tmp_run_out = os.path.join(tmp_dir, f"_tmp_run_{targets_tag}_{mu_tag}_{sigma_tag}_{dist_tag}.csv")
                    tmp_roi_out = os.path.join(tmp_dir, f"_tmp_roi_{targets_tag}_{mu_tag}_{sigma_tag}_{dist_tag}.csv")

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
                            "targets": targets_str,
                            "target_channel": targets_str,
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

    except Exception as e:
        print("\n===== ERROR OCCURRED =====")
        print(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
