# src/main.py
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import List, Optional

import pandas as pd

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


# ---------------------------------------------------------------------------
# Experiment config (inlined from former experiment.py)
# ---------------------------------------------------------------------------

@dataclass
class ExperimentConfig:
    project_root: str
    data_csv: str
    src_dir: str
    output_dir: str
    output_file: str
    channels: List[str]
    spend_cols: List[str]
    mu0: float
    sigma0: float
    multipliers: List[float]
    roi_mu_values: List[float]
    roi_sigma_values: List[float]
    roi_dist_values: List[str]


def _compute_mu0(df: pd.DataFrame, kpi_col: str, spend_cols: List[str]) -> float:
    total_spend = df[spend_cols].sum(axis=1)
    return float((df[kpi_col] / total_spend).median())


def _compute_sigma0(df: pd.DataFrame, kpi_col: str, spend_cols: List[str]) -> float:
    total_spend = df[spend_cols].sum(axis=1)
    return float((df[kpi_col] / total_spend).std())


def _make_mu_grid(mu0: float, multipliers: List[float], digits: int = 6) -> List[float]:
    return [round(mu0 * m, digits) for m in multipliers]


def _make_sigma_grid(sigma0: float, multipliers: List[float], digits: int = 6) -> List[float]:
    return [round(sigma0 * m, digits) for m in multipliers]


def build_experiment_config(
    channels: List[str],
    multipliers: List[float],
    kpi_col: str = "subscriptions",
    spend_suffix: str = "_spend",
    mu_grid: list = None,
    sigma_grid: list = None,
    dist_grid: list = None,
    output_file: Optional[str] = None,
    data_csv: Optional[str] = None,
) -> ExperimentConfig:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if data_csv is None:
        data_csv = os.path.join(project_root, "data", "raw", "monthly_mocha.csv")
    if not os.path.exists(data_csv):
        raise FileNotFoundError(f"Data CSV not found at {data_csv}.")

    src_dir = os.path.join(project_root, "src")
    output_dir = os.path.join(project_root, "data", "output")
    os.makedirs(output_dir, exist_ok=True)

    if output_file is None:
        output_file = "prior_sensitivity_results.csv"
    if not os.path.isabs(output_file):
        output_file = os.path.join(output_dir, output_file)

    df = pd.read_csv(data_csv)
    spend_cols = [f"{ch}{spend_suffix}" for ch in channels]
    missing = [c for c in spend_cols if c not in df.columns]
    if missing:
        raise KeyError(
            "Missing spend columns in CSV: "
            + ", ".join(missing)
            + "\nAvailable columns: "
            + ", ".join(df.columns)
        )

    mu0 = _compute_mu0(df, kpi_col=kpi_col, spend_cols=spend_cols)
    roi_mu_values = _make_mu_grid(mu0, multipliers) if mu_grid is None else mu_grid

    sigma0 = _compute_sigma0(df, kpi_col=kpi_col, spend_cols=spend_cols)
    roi_sigma_values = _make_sigma_grid(sigma0, multipliers) if sigma_grid is None else sigma_grid

    roi_dist_values = ["LogNormal"] if dist_grid is None else dist_grid

    return ExperimentConfig(
        project_root=project_root,
        data_csv=data_csv,
        src_dir=src_dir,
        output_dir=output_dir,
        output_file=output_file,
        channels=channels,
        spend_cols=spend_cols,
        mu0=mu0,
        sigma0=sigma0,
        multipliers=multipliers,
        roi_mu_values=roi_mu_values,
        roi_sigma_values=roi_sigma_values,
        roi_dist_values=roi_dist_values,
    )


# ---------------------------------------------------------------------------

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


def _contains_close(values: list[float], target: float, tol: float = 1e-9) -> bool:
    return any(abs(float(v) - float(target)) <= tol for v in values)


def _nearest_value(values: list[float], reference: float) -> float:
    if not values:
        raise ValueError("Cannot choose nearest value from an empty list.")
    return float(min((float(v) for v in values), key=lambda x: (abs(x - float(reference)), x)))


def _pick_preferred_dist(dist_values: list[str]) -> str:
    if not dist_values:
        raise ValueError("Distribution grid is empty.")
    for d in dist_values:
        if str(d).strip().lower() == "lognormal":
            return str(d)
    return str(dist_values[0])


def _resolve_baseline_from_config(cfg, run_cfg: dict) -> tuple[float, float, str]:
    baseline_cfg = run_cfg.get("baseline", {}) or {}

    baseline_mu_cfg = baseline_cfg.get("roi_mu")
    if baseline_mu_cfg is None:
        baseline_mu = _nearest_value(cfg.roi_mu_values, cfg.mu0)
    else:
        baseline_mu = round(float(baseline_mu_cfg), 6)
        if not _contains_close(cfg.roi_mu_values, baseline_mu):
            raise ValueError(
                "Configured baseline.roi_mu is not in the active mu grid. "
                f"baseline.roi_mu={baseline_mu}, active mu grid={cfg.roi_mu_values}"
            )

    baseline_sigma_cfg = baseline_cfg.get("roi_sigma")
    if baseline_sigma_cfg is None:
        baseline_sigma = _nearest_value(cfg.roi_sigma_values, cfg.sigma0)
    else:
        baseline_sigma = round(float(baseline_sigma_cfg), 6)
        if not _contains_close(cfg.roi_sigma_values, baseline_sigma):
            raise ValueError(
                "Configured baseline.roi_sigma is not in the active sigma grid. "
                f"baseline.roi_sigma={baseline_sigma}, active sigma grid={cfg.roi_sigma_values}"
            )

    dist_values = [str(x) for x in cfg.roi_dist_values]
    baseline_dist_cfg = baseline_cfg.get("roi_dist")
    if baseline_dist_cfg is None:
        baseline_dist = _pick_preferred_dist(dist_values)
    else:
        wanted = str(baseline_dist_cfg).strip().lower()
        mapped = {str(d).strip().lower(): str(d) for d in dist_values}
        if wanted not in mapped:
            raise ValueError(
                "Configured baseline.roi_dist is not in the active dist grid. "
                f"baseline.roi_dist={baseline_dist_cfg}, active dist grid={dist_values}"
            )
        baseline_dist = mapped[wanted]

    return round(float(baseline_mu), 6), round(float(baseline_sigma), 6), str(baseline_dist)


def _sanitize_tag_token(raw: str) -> str:
    s = str(raw).strip().lower()
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in {"-", "_"}:
            out.append(ch)
        else:
            out.append("_")
    token = "".join(out).strip("_")
    while "__" in token:
        token = token.replace("__", "_")
    return token or "dataset"


def _resolve_data_tag(*, data_csv: str, geo_col: str | None, explicit_data_tag: str | None) -> str | None:
    if explicit_data_tag:
        return _sanitize_tag_token(explicit_data_tag)
    if geo_col:
        return _sanitize_tag_token(Path(data_csv).stem)
    return None


def _resolve_runner_python(project_root: str) -> str:
    forced = os.environ.get("BLUEALPHA_PYTHON")
    if forced and os.path.exists(forced):
        return forced

    current = sys.executable

    venv_py = os.path.join(project_root, ".venv", "Scripts", "python.exe")
    if os.path.exists(venv_py):
        print(f"[info] Using project virtualenv interpreter for Meridian runs: {venv_py}")
        return venv_py

    return current


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
    runner_python = _resolve_runner_python(project_root)
    ensure_output_dirs()

    config_path = _extract_config_path(sys.argv[1:])
    if config_path and not os.path.isabs(config_path):
        config_path = os.path.join(project_root, config_path)

    run_cfg = load_run_config(config_path)
    sampler = run_cfg["sampler"]

    model_cfg = run_cfg.get("model", {})
    channels = [str(x) for x in model_cfg["channels"]]
    multipliers = [float(x) for x in run_cfg["experiment"]["multipliers"]]
    mu_grid = run_cfg["experiment"].get("roi_mu_values")
    sigma_grid = run_cfg["experiment"].get("roi_sigma_values")
    dist_grid = [str(x) for x in run_cfg["experiment"].get("roi_dist_values", ["LogNormal"])]

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

    kpi_col = str(model_cfg.get("kpi_col", "subscriptions"))
    time_col = str(model_cfg.get("time_col", "date"))
    explicit_data_tag = model_cfg.get("data_tag")
    if explicit_data_tag is not None:
        explicit_data_tag = str(explicit_data_tag)
    geo_col = model_cfg.get("geo_col")
    if geo_col is not None:
        geo_col = str(geo_col)
    population_col = model_cfg.get("population_col")
    if population_col is not None:
        population_col = str(population_col)
    default_targets = [str(x) for x in run_cfg.get("defaults", {}).get("targets", ["tiktok"])]

    data_csv_cfg = str(model_cfg.get("data_csv", "data/raw/monthly_mocha.csv"))
    if os.path.isabs(data_csv_cfg):
        data_csv = data_csv_cfg
    else:
        data_csv = os.path.join(project_root, data_csv_cfg)
    if not os.path.exists(data_csv):
        raise FileNotFoundError(f"Configured data CSV does not exist: {data_csv}")

    output_dir = str(RUNS_DIR)
    os.makedirs(output_dir, exist_ok=True)

    _, _, targets, csv_override = parse_channels_and_output(
        full_channels=channels,
        output_dir=output_dir,
        default_target=default_targets,
    )
    if csv_override:
        data_csv_cli = str(csv_override)
        data_csv = data_csv_cli if os.path.isabs(data_csv_cli) else os.path.join(project_root, data_csv_cli)
        if not os.path.exists(data_csv):
            raise FileNotFoundError(f"CLI --csv path does not exist: {data_csv}")
    cfg = build_experiment_config(
        channels=channels,
        multipliers=multipliers,
        kpi_col=kpi_col,
        data_csv=data_csv,
        mu_grid=mu_grid,
        sigma_grid=sigma_grid,
        dist_grid=dist_grid,
        output_file="prior_sensitivity_results.csv",
    )
    if not targets:
        raise ValueError("No targets provided. Pass --targets <channel...> or --channels <channel...>.")

    targets = sorted(str(x) for x in targets)
    targets_tag = "_".join(targets)
    data_tag = _resolve_data_tag(data_csv=data_csv, geo_col=geo_col, explicit_data_tag=explicit_data_tag)
    output_tag = f"{targets_tag}__{data_tag}" if data_tag else targets_tag
    targets_str = ",".join(targets)

    run_output_file = str(run_csv_path(output_tag, RUNS_DIR))
    roi_output_file = str(roi_csv_path(output_tag, RUNS_DIR))
    tmp_dir = os.path.dirname(run_output_file)
    os.makedirs(tmp_dir, exist_ok=True)

    channels_json = json.dumps(channels)

    print("Spend cols used:", cfg.spend_cols)
    print("Computed mu0 =", round(cfg.mu0, 6))
    print("Computed sigma0 =", round(cfg.sigma0, 6))
    print(
        "Mu grid source =",
        "experiment.roi_mu_values (manual)" if mu_grid is not None else "mu0 * experiment.multipliers (auto)",
    )
    print(
        "Sigma grid source =",
        "experiment.roi_sigma_values (manual)" if sigma_grid is not None else "sigma0 * experiment.multipliers (auto)",
    )
    if mu_grid is not None or sigma_grid is not None:
        print(
            "Grid precedence note: explicit experiment.roi_mu_values / roi_sigma_values override multipliers "
            "for those dimensions."
        )
    print("Mu grid =", cfg.roi_mu_values)
    print("Sigma grid =", cfg.roi_sigma_values)
    print("Dist grid =", cfg.roi_dist_values)
    print("Alpha_m grid =", structural_grids["alpha_m"])
    print("Ec_m grid =", structural_grids["ec_m"])
    print("Slope_m grid =", structural_grids["slope_m"])
    print("Max lag grid =", structural_grids["max_lag"])
    print("Adstock decay grid =", structural_grids["adstock_decay"])
    print("Input data CSV =", data_csv)
    if data_tag:
        print("Data tag =", data_tag)
        print("Output tag =", output_tag)
    print("KPI col =", kpi_col)
    print("Time col =", time_col)
    print("Geo col =", geo_col if geo_col is not None else "(auto/national)")
    print("Population col =", population_col if population_col is not None else "(none/auto)")
    print("Run output file:", run_output_file)
    print("ROI output file:", roi_output_file)

    baseline_mu, baseline_sigma, baseline_dist = _resolve_baseline_from_config(cfg, run_cfg)
    baseline_structural = {
        "alpha_m": structural_grids["alpha_m"][0],
        "ec_m": structural_grids["ec_m"][0],
        "slope_m": structural_grids["slope_m"][0],
        "max_lag": structural_grids["max_lag"][0],
        "adstock_decay_spec": structural_grids["adstock_decay"][0],
    }
    official_outdir = os.path.join(
        project_root,
        "data",
        "output",
        "03_reports",
        "report",
        output_tag,
        "figures",
        "meridian_official",
    )
    official_manifest = os.path.join(official_outdir, "manifest.json")
    official_export_done = os.path.exists(official_manifest)
    print(
        "Baseline (effective) =",
        {"mu": baseline_mu, "sigma": baseline_sigma, "dist": baseline_dist},
    )

    already_done = load_resume_state(run_output_file)
    for legacy_path in candidate_run_csv_paths(output_tag)[1:]:
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
        scope_key = f"multi|{targets_str}"
        if data_tag:
            scope_key = f"{scope_key}|data={data_tag}"
        run_key = build_run_id(
            scope_key,
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
                output_tag,
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
            runner_python,
            "-m",
            "src.run_meridian_once",
            "--csv",
            data_csv,
            "--kpi_col",
            kpi_col,
            "--time_col",
            time_col,
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
        if geo_col:
            cmd.extend(["--geo_col", geo_col])
        if population_col:
            cmd.extend(["--population_col", population_col])

        is_baseline_grid_point = (
            abs(float(mu) - float(baseline_mu)) <= 1e-9
            and abs(float(sigma) - float(baseline_sigma)) <= 1e-9
            and str(dist) == str(baseline_dist)
            and (
                (alpha_m is None and baseline_structural["alpha_m"] is None)
                or (alpha_m is not None and baseline_structural["alpha_m"] is not None and abs(float(alpha_m) - float(baseline_structural["alpha_m"])) <= 1e-9)
            )
            and (
                (ec_m is None and baseline_structural["ec_m"] is None)
                or (ec_m is not None and baseline_structural["ec_m"] is not None and abs(float(ec_m) - float(baseline_structural["ec_m"])) <= 1e-9)
            )
            and abs(float(slope_m) - float(baseline_structural["slope_m"])) <= 1e-9
            and int(max_lag) == int(baseline_structural["max_lag"])
            and str(adstock_decay) == str(baseline_structural["adstock_decay_spec"])
        )
        if is_baseline_grid_point and not official_export_done:
            cmd.extend([
                "--official_outdir",
                official_outdir,
                "--official_time_granularity",
                "quarterly",
            ])

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
        if is_baseline_grid_point:
            official_export_done = True

        print("Iteration time:", round(time.time() - t0, 2), "seconds")
        run_index += 1

    print("\nALL RUNS COMPLETED.")
    print("Saved run diagnostics to:", run_output_file)
    print("Saved ROI results to:", roi_output_file)


if __name__ == "__main__":
    main()
