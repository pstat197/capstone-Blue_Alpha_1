# src/main.py
import json
import os
import subprocess
import sys
import time
from itertools import product

from src.experiment import build_experiment_config
from src.io_utils import (
    ROI_OUTPUT_COLUMNS,
    RUN_OUTPUT_COLUMNS,
    append_tmp_to_output,
    load_resume_state,
    parse_channels_and_output,
)
from src.output_paths import (
    RUNS_DIR,
    candidate_run_csv_paths,
    ensure_output_dirs,
    roi_csv_path,
    run_csv_path,
)
from src.run_config import load_run_config


def _extract_config_path(argv: list[str]) -> str | None:
    for i, token in enumerate(argv):
        if token == "--config" and i + 1 < len(argv):
            return argv[i + 1]
        if token.startswith("--config="):
            return token.split("=", 1)[1]
    return None


def _cast_list(value, default, *, cast=None, lower: bool = False, keep_none: bool = False):
    if value is None:
        raw = list(default)
    elif isinstance(value, list):
        raw = value if value else list(default)
    else:
        raw = [value]

    out = []
    for x in raw:
        if x is None and keep_none:
            out.append(None)
            continue
        y = cast(x) if cast else x
        if lower:
            y = str(y).strip().lower()
        out.append(y)
    return out


def _struct_token(value, prefix: str) -> str:
    if value is None:
        return f"{prefix}default"
    if isinstance(value, (int, float)):
        return f"{prefix}{str(round(float(value), 6)).replace('.', 'p')}"
    return f"{prefix}{value}"


def _is_default_structural(alpha_m, ec_m, slope_m, max_lag, adstock_decay) -> bool:
    slope_is_default = slope_m is None or abs(float(slope_m) - 1.0) < 1e-12
    return (
        alpha_m is None
        and ec_m is None
        and slope_is_default
        and int(max_lag) == 8
        and str(adstock_decay) == "geometric"
    )


def build_run_id(
    scope: str,
    mu: float,
    sigma: float,
    dist: str,
    *,
    alpha_m=None,
    ec_m=None,
    slope_m=1.0,
    max_lag=8,
    adstock_decay="geometric",
) -> str:
    base = f"{scope}|{float(mu):.6f}|{float(sigma):.6f}|{str(dist)}"
    if _is_default_structural(alpha_m, ec_m, slope_m, max_lag, adstock_decay):
        return base
    return (
        f"{base}|"
        f"{_struct_token(alpha_m, 'alpha=')}|"
        f"{_struct_token(ec_m, 'ec=')}|"
        f"{_struct_token(slope_m, 'slope=')}|"
        f"lag={int(max_lag)}|"
        f"decay={adstock_decay}"
    )


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ensure_output_dirs()

    config_path = _extract_config_path(sys.argv[1:])
    if config_path and not os.path.isabs(config_path):
        config_path = os.path.join(project_root, config_path)

    run_cfg = load_run_config(config_path)
    sampler = run_cfg["sampler"]

    channels = [str(x) for x in run_cfg["model"]["channels"]]
    multipliers = [float(x) for x in run_cfg["experiment"]["multipliers"]]
    mu_grid = run_cfg["experiment"].get("roi_mu_values")
    sigma_grid = run_cfg["experiment"].get("roi_sigma_values")
    dist_grid = [str(x) for x in run_cfg["experiment"].get("roi_dist_values", ["Normal", "LogNormal"])]

    if mu_grid is not None:
        mu_grid = [float(x) for x in mu_grid]
    if sigma_grid is not None:
        sigma_grid = [float(x) for x in sigma_grid]

    structural_cfg = run_cfg.get("structural", {})
    structural_grids = {
        "alpha_m": _cast_list(structural_cfg.get("alpha_m_values"), [None], cast=float, keep_none=True),
        "ec_m": _cast_list(structural_cfg.get("ec_m_values"), [None], cast=float, keep_none=True),
        "slope_m": _cast_list(structural_cfg.get("slope_m_values"), [1.0], cast=float),
        "max_lag": _cast_list(structural_cfg.get("max_lag_values"), [8], cast=int),
        "adstock_decay": _cast_list(structural_cfg.get("adstock_decay_values"), ["geometric"], lower=True),
    }

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
    output_dir = str(RUNS_DIR)
    os.makedirs(output_dir, exist_ok=True)

    _, _, targets, _ = parse_channels_and_output(
        full_channels=channels,
        output_dir=output_dir,
        default_target=default_targets,
    )
    if not targets:
        raise ValueError("No targets provided. Pass --targets <channel...> or --channels <channel...>.")

    targets = sorted(str(x) for x in targets)
    targets_tag = "_".join(targets)
    targets_str = ",".join(targets)

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
    print("Alpha_m grid =", structural_grids["alpha_m"])
    print("Ec_m grid =", structural_grids["ec_m"])
    print("Slope_m grid =", structural_grids["slope_m"])
    print("Max lag grid =", structural_grids["max_lag"])
    print("Adstock decay grid =", structural_grids["adstock_decay"])
    print("Run output file:", run_output_file)
    print("ROI output file:", roi_output_file)

    baseline_mu = cfg.mu0
    baseline_sigma = cfg.roi_sigma_values[min(1, len(cfg.roi_sigma_values) - 1)]
    baseline_dist = cfg.roi_dist_values[0]
    baseline_structural = {
        "alpha_m": structural_grids["alpha_m"][0],
        "ec_m": structural_grids["ec_m"][0],
        "slope_m": structural_grids["slope_m"][0],
        "max_lag": structural_grids["max_lag"][0],
        "adstock_decay_spec": structural_grids["adstock_decay"][0],
    }

    already_done = load_resume_state(run_output_file)
    for legacy_path in candidate_run_csv_paths(targets_tag)[1:]:
        legacy_run_output_file = str(legacy_path)
        if legacy_run_output_file != run_output_file and os.path.exists(legacy_run_output_file):
            already_done.update(load_resume_state(legacy_run_output_file))

    env = os.environ.copy()
    env["TF_CPP_MIN_LOG_LEVEL"] = "3"
    env["TF_ENABLE_ONEDNN_OPTS"] = "0"

    print("MODE: LINKED TARGET-SET (UNIFIED)")
    print("Targets to perturb together:", targets_str)

    total_runs = (
        len(cfg.roi_mu_values)
        * len(cfg.roi_sigma_values)
        * len(cfg.roi_dist_values)
        * len(structural_grids["alpha_m"])
        * len(structural_grids["ec_m"])
        * len(structural_grids["slope_m"])
        * len(structural_grids["max_lag"])
        * len(structural_grids["adstock_decay"])
    )

    run_index = 1
    grid_iter = product(
        cfg.roi_mu_values,
        cfg.roi_sigma_values,
        cfg.roi_dist_values,
        structural_grids["alpha_m"],
        structural_grids["ec_m"],
        structural_grids["slope_m"],
        structural_grids["max_lag"],
        structural_grids["adstock_decay"],
    )

    for mu, sigma, dist, alpha_m, ec_m, slope_m, max_lag, adstock_decay in grid_iter:
        mu = round(float(mu), 6)
        sigma = round(float(sigma), 6)
        dist = str(dist)
        alpha_m = None if alpha_m is None else round(float(alpha_m), 6)
        ec_m = None if ec_m is None else round(float(ec_m), 6)
        slope_m = round(float(slope_m), 6)
        max_lag = int(max_lag)
        adstock_decay = str(adstock_decay).strip().lower()

        roi_overrides = {ch: {"mu": mu, "sigma": sigma, "dist": dist} for ch in targets}
        structural_overrides = {
            "alpha_m": alpha_m,
            "ec_m": ec_m,
            "slope_m": slope_m,
            "max_lag": max_lag,
            "adstock_decay_spec": adstock_decay,
        }
        prior_key = json.dumps(
            {
                "roi_prior_overrides": roi_overrides,
                "structural_overrides": structural_overrides,
            },
            sort_keys=True,
        )
        run_key = build_run_id(
            f"multi|{targets_str}",
            mu,
            sigma,
            dist,
            alpha_m=alpha_m,
            ec_m=ec_m,
            slope_m=slope_m,
            max_lag=max_lag,
            adstock_decay=adstock_decay,
        )

        if run_key in already_done:
            print(
                "Skipping"
                f" targets={targets_str}, mu={mu}, sigma={sigma}, dist={dist},"
                f" alpha={alpha_m}, ec={ec_m}, slope={slope_m}, max_lag={max_lag}, decay={adstock_decay}"
            )
            run_index += 1
            continue

        print(f"\n===== Run {run_index}/{total_runs} =====")
        print(
            f"Targets: {targets_str}, Prior mu: {mu}, Prior sigma: {sigma}, Dist: {dist}, "
            f"alpha={alpha_m}, ec={ec_m}, slope={slope_m}, max_lag={max_lag}, decay={adstock_decay}"
        )

        t0 = time.time()
        run_suffix = "_".join(
            [
                targets_tag,
                str(mu).replace(".", "p"),
                str(sigma).replace(".", "p"),
                dist,
                _struct_token(alpha_m, "a"),
                _struct_token(ec_m, "ec"),
                _struct_token(slope_m, "s"),
                _struct_token(max_lag, "lag"),
                _struct_token(adstock_decay, "decay"),
            ]
        )
        tmp_run_out = os.path.join(tmp_dir, f"_tmp_run_{run_suffix}.csv")
        tmp_roi_out = os.path.join(tmp_dir, f"_tmp_roi_{run_suffix}.csv")

        cmd = [
            sys.executable,
            "-m",
            "src.run_meridian_once",
            "--csv",
            data_csv,
            "--channels_json",
            channels_json,
            "--roi_prior_overrides_json",
            json.dumps(roi_overrides, sort_keys=True),
            "--structural_overrides_json",
            json.dumps(structural_overrides, sort_keys=True),
            "--prior_key",
            prior_key,
            "--out_run_csv",
            tmp_run_out,
            "--out_roi_csv",
            tmp_roi_out,
            "--baseline_mu",
            str(baseline_mu),
            "--baseline_sigma",
            str(baseline_sigma),
            "--baseline_dist",
            str(baseline_dist),
            "--baseline_structural_overrides_json",
            json.dumps(baseline_structural, sort_keys=True),
            "--n_chains",
            str(int(sampler["n_chains"])),
            "--n_adapt",
            str(int(sampler["n_adapt"])),
            "--n_burnin",
            str(int(sampler["n_burnin"])),
            "--n_keep",
            str(int(sampler["n_keep"])),
            "--seed",
            str(int(sampler["seed"])),
        ]

        proc = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            print("\n--- Subprocess STDOUT ---\n", proc.stdout)
            print("\n--- Subprocess STDERR ---\n", proc.stderr)
            raise RuntimeError(f"Subprocess failed with code {proc.returncode}")

        ensure_cols = {
            "run_id": run_key,
            "prior_key": prior_key,
            "targets": targets_str,
            "target_channel": targets_str,
        }
        append_tmp_to_output(
            tmp_out=tmp_run_out,
            output_file=run_output_file,
            ensure_cols=ensure_cols,
            expected_columns=RUN_OUTPUT_COLUMNS,
            cast_single_target=False,
            normalize_part=True,
        )
        append_tmp_to_output(
            tmp_out=tmp_roi_out,
            output_file=roi_output_file,
            ensure_cols=ensure_cols,
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
