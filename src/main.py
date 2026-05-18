# src/main.py
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    ensure_output_dirs,
    roi_csv_path,
    run_csv_path,
)
from src.run_config import ROI_PRIOR_POLICY_ERROR, load_run_config

CONTRIBUTION_PRIOR_MODE = "contribution"


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
    roi_mu_values: List[float]
    roi_sigma_values: List[float]
    roi_dist_values: List[str]

def build_experiment_config(
    channels: List[str],
    roi_mu_values: List[float],
    roi_sigma_values: List[float],
    roi_dist_values: List[str],
    kpi_col: str = "subscriptions",
    spend_suffix: str = "_spend",
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

    roi_mu_values = [round(float(v), 6) for v in roi_mu_values]
    roi_sigma_values = [round(float(v), 6) for v in roi_sigma_values]
    roi_dist_values = [str(v) for v in roi_dist_values]

    return ExperimentConfig(
        project_root=project_root,
        data_csv=data_csv,
        src_dir=src_dir,
        output_dir=output_dir,
        output_file=output_file,
        channels=channels,
        spend_cols=spend_cols,
        roi_mu_values=roi_mu_values,
        roi_sigma_values=roi_sigma_values,
        roi_dist_values=roi_dist_values,
    )


def _infer_kpi_type_from_name(kpi_col: str) -> str:
    k = str(kpi_col or "").strip().lower()
    revenue_tokens = ("revenue", "sales", "gmv", "income", "turnover")
    return "revenue" if any(tok in k for tok in revenue_tokens) else "non_revenue"


def _as_optional_float(raw) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in {"", "null", "none", "nan"}:
        return None
    return float(raw)


def _load_dataset_context(data_csv: str, channels: list[str], kpi_col: str) -> dict:
    df = pd.read_csv(data_csv)
    if kpi_col not in df.columns:
        raise ValueError(f"KPI column '{kpi_col}' is missing from dataset: {data_csv}")

    kpi_series = pd.to_numeric(df[kpi_col], errors="coerce")
    if kpi_series.isna().all():
        raise ValueError(f"KPI column '{kpi_col}' has no numeric values in dataset: {data_csv}")

    spend_by_channel: dict[str, float] = {}
    missing_spend_cols: list[str] = []
    for ch in channels:
        spend_col = f"{ch}_spend"
        if spend_col not in df.columns:
            missing_spend_cols.append(spend_col)
            continue
        spend_by_channel[ch] = float(pd.to_numeric(df[spend_col], errors="coerce").fillna(0).sum())
    if missing_spend_cols:
        raise ValueError(
            "Missing spend columns in dataset: "
            + ", ".join(missing_spend_cols)
            + ". Expected naming pattern '<channel>_spend'."
        )

    return {
        "kpi_sum": float(kpi_series.fillna(0).sum()),
        "spend_by_channel": spend_by_channel,
    }


def _resolve_outcome_plan(run_cfg: dict, model_cfg: dict) -> dict:
    outcome_cfg = run_cfg.get("outcome", {}) or {}
    kpi_col = str(outcome_cfg.get("kpi_col") or model_cfg.get("kpi_col") or "subscriptions")
    raw_kpi_type = str(outcome_cfg.get("kpi_type", "auto")).strip().lower()
    if raw_kpi_type not in {"auto", "revenue", "non_revenue"}:
        raise ValueError("outcome.kpi_type must be one of: auto, revenue, non_revenue.")

    revenue_per_kpi = _as_optional_float(outcome_cfg.get("revenue_per_kpi"))
    if revenue_per_kpi is not None and revenue_per_kpi <= 0:
        raise ValueError("outcome.revenue_per_kpi must be > 0 when provided.")

    rpk_values_raw = outcome_cfg.get("revenue_per_kpi_values")
    revenue_per_kpi_values: list[float] = []
    if isinstance(rpk_values_raw, list):
        for v in rpk_values_raw:
            fv = float(v)
            if fv <= 0:
                raise ValueError("outcome.revenue_per_kpi_values must contain only > 0 values.")
            revenue_per_kpi_values.append(round(fv, 6))
    elif rpk_values_raw not in (None, "", "null", "none"):
        fv = float(rpk_values_raw)
        if fv <= 0:
            raise ValueError("outcome.revenue_per_kpi_values must contain only > 0 values.")
        revenue_per_kpi_values.append(round(fv, 6))

    if revenue_per_kpi is not None and not any(abs(v - revenue_per_kpi) <= 1e-9 for v in revenue_per_kpi_values):
        revenue_per_kpi_values = [round(revenue_per_kpi, 6), *revenue_per_kpi_values]
    revenue_per_kpi_values = sorted(set(revenue_per_kpi_values))

    if raw_kpi_type == "auto":
        if revenue_per_kpi is not None or revenue_per_kpi_values:
            kpi_type = "non_revenue"
        else:
            kpi_type = _infer_kpi_type_from_name(kpi_col)
    else:
        kpi_type = raw_kpi_type

    if kpi_type == "revenue":
        scenarios = [None]
    elif revenue_per_kpi_values:
        scenarios = revenue_per_kpi_values
    elif revenue_per_kpi is not None:
        scenarios = [round(revenue_per_kpi, 6)]
    else:
        scenarios = [None]

    return {
        "kpi_col": kpi_col,
        "kpi_type": kpi_type,
        "revenue_per_kpi": None if revenue_per_kpi is None else round(revenue_per_kpi, 6),
        "revenue_per_kpi_values": scenarios,
    }


def _resolve_effective_prior_mode(run_cfg: dict, *, kpi_type: str, revenue_per_kpi: float | None) -> str:
    mode = str(run_cfg.get("prior_mode", "auto")).strip().lower()
    if mode == CONTRIBUTION_PRIOR_MODE:
        raise ValueError("This one-channel prior sensitivity workflow is ROI-prior only; contribution prior mode is not supported.")
    if mode not in {"auto", "roi"}:
        raise ValueError("prior_mode must be one of: auto, roi.")
    if kpi_type == "non_revenue" and revenue_per_kpi is None:
        raise ValueError(ROI_PRIOR_POLICY_ERROR)
    return "roi"


def _resolve_prior_label(*, effective_prior_mode: str, kpi_type: str, revenue_per_kpi: float | None) -> str:
    if effective_prior_mode != "roi":
        raise ValueError("This one-channel prior sensitivity workflow is ROI-prior only.")
    if revenue_per_kpi is not None:
        return "Revenue-equivalent ROI"
    return "ROI"


def _roi_grid_from_config(run_cfg: dict) -> dict:
    active_prior = run_cfg.get("active_prior_grids", {}) or {}
    roi_cfg = (active_prior.get("roi", {}) or {})
    mu_vals = [round(float(v), 6) for v in roi_cfg.get("roi_mu_values", run_cfg.get("experiment", {}).get("roi_mu_values", []))]
    sigma_vals = [round(float(v), 6) for v in roi_cfg.get("roi_sigma_values", run_cfg.get("experiment", {}).get("roi_sigma_values", []))]
    dist_vals = [str(v) for v in roi_cfg.get("roi_dist_values", run_cfg.get("experiment", {}).get("roi_dist_values", ["LogNormal"]))]
    if not mu_vals or not sigma_vals or not dist_vals:
        raise ValueError("ROI prior grid is incomplete. Check run_mode grid settings.")
    return {"mu": mu_vals, "sigma": sigma_vals, "dist": dist_vals}


def _roi_grid_for_target(run_cfg: dict, target_channel: str) -> dict | None:
    channel_grids = (run_cfg.get("active_prior_grids", {}) or {}).get("roi_by_channel", {}) or {}
    channel_grid = channel_grids.get(target_channel)
    if not isinstance(channel_grid, dict):
        return _roi_grid_from_config(run_cfg)
    if not channel_grid.get("enabled", True):
        return None

    mu_vals = [round(float(v), 6) for v in channel_grid.get("roi_mu_values", [])]
    sigma_vals = [round(float(v), 6) for v in channel_grid.get("roi_sigma_values", [])]
    dist_vals = [str(v) for v in channel_grid.get("roi_dist_values", [])]
    if not mu_vals or not sigma_vals or not dist_vals:
        raise ValueError(f"ROI prior grid is incomplete for target channel '{target_channel}'.")
    return {"mu": mu_vals, "sigma": sigma_vals, "dist": dist_vals}


def _filter_prior_run_points_to_baseline_only(run_cfg: dict, prior_run_points: list[dict]) -> list[dict]:
    if not prior_run_points:
        return []

    filtered: list[dict] = []
    for point in prior_run_points:
        target_channel = str(point.get("target_channel") or "")
        roi_grid = _roi_grid_for_target(run_cfg, target_channel)
        if roi_grid is None:
            continue
        baseline_mu, baseline_sigma, baseline_dist = _resolve_roi_baseline_from_grid(
            roi_grid["mu"], roi_grid["sigma"], roi_grid["dist"], run_cfg
        )
        if (
            abs(float(point["roi_mu_display"]) - baseline_mu) <= 1e-9
            and abs(float(point["roi_sigma_display"]) - baseline_sigma) <= 1e-9
            and str(point["roi_dist_display"]) == str(baseline_dist)
        ):
            filtered.append(point)

    if not filtered:
        raise ValueError("No baseline prior run point matched the active baseline settings.")
    return filtered


def _is_baseline_prior_point(run_cfg: dict, prior_point: dict) -> bool:
    mode = str(prior_point.get("effective_prior_mode", "") or "").strip().lower()
    if mode != "roi":
        return False
    roi_grid = _roi_grid_for_target(run_cfg, str(prior_point.get("target_channel") or ""))
    if roi_grid is None:
        return False
    baseline_mu, baseline_sigma, baseline_dist = _resolve_roi_baseline_from_grid(
        roi_grid["mu"], roi_grid["sigma"], roi_grid["dist"], run_cfg
    )
    return (
        abs(float(prior_point["roi_mu_display"]) - baseline_mu) <= 1e-9
        and abs(float(prior_point["roi_sigma_display"]) - baseline_sigma) <= 1e-9
        and str(prior_point["roi_dist_display"]) == str(baseline_dist)
    )


def _build_structural_run_points(structural_grids: dict[str, list], structural_grid_scope: str) -> tuple[list[dict], dict]:
    baseline_structural = {
        "alpha_m": structural_grids["alpha_m"][0],
        "ec_m": structural_grids["ec_m"][0],
        "slope_m": structural_grids["slope_m"][0],
        "max_lag": structural_grids["max_lag"][0],
        "adstock_decay_spec": structural_grids["adstock_decay"][0],
    }
    if structural_grid_scope == "full_grid":
        structural_points = [
            {
                "alpha_m": alpha_m,
                "ec_m": ec_m,
                "slope_m": slope_m,
                "max_lag": max_lag,
                "adstock_decay_spec": adstock_decay,
            }
            for alpha_m, ec_m, slope_m, max_lag, adstock_decay in product(
                structural_grids["alpha_m"],
                structural_grids["ec_m"],
                structural_grids["slope_m"],
                structural_grids["max_lag"],
                structural_grids["adstock_decay"],
            )
        ]
        return structural_points, baseline_structural

    structural_points = [dict(baseline_structural)]
    axis_order = [
        ("alpha_m", structural_grids["alpha_m"]),
        ("ec_m", structural_grids["ec_m"]),
        ("slope_m", structural_grids["slope_m"]),
        ("max_lag", structural_grids["max_lag"]),
        ("adstock_decay_spec", structural_grids["adstock_decay"]),
    ]
    for axis_name, values in axis_order:
        baseline_value = baseline_structural[axis_name]
        for value in values[1:]:
            if value == baseline_value:
                continue
            point = dict(baseline_structural)
            point[axis_name] = value
            structural_points.append(point)
    return structural_points, baseline_structural


def _structural_signature(point: dict) -> tuple:
    alpha_m = point.get("alpha_m")
    ec_m = point.get("ec_m")
    return (
        None if alpha_m is None else round(float(alpha_m), 6),
        None if ec_m is None else round(float(ec_m), 6),
        round(float(point.get("slope_m", 1.0)), 6),
        int(point.get("max_lag", 8)),
        str(point.get("adstock_decay_spec", "geometric")).strip().lower(),
    )


def _build_execution_pairs(
    *,
    run_cfg: dict,
    prior_run_points: list[dict],
    structural_run_points: list[dict],
    baseline_structural: dict,
    structural_grid_scope: str,
) -> tuple[list[tuple[dict, dict, str]], dict]:
    if structural_grid_scope != "one_at_a_time":
        pairs = [
            (prior_point, structural_point, "prior_sweep")
            for prior_point, structural_point in product(prior_run_points, structural_run_points)
        ]
        return pairs, {
            "mode": "cartesian",
            "stage1_prior_points": len(prior_run_points),
            "stage2_baseline_prior_points": 0,
            "stage2_structural_points": 0,
        }

    baseline_prior_points = _filter_prior_run_points_to_baseline_only(run_cfg, prior_run_points)
    baseline_signature = _structural_signature(baseline_structural)
    non_baseline_structural = [
        structural_point
        for structural_point in structural_run_points
        if _structural_signature(structural_point) != baseline_signature
    ]

    pairs = [(prior_point, dict(baseline_structural), "prior_sweep") for prior_point in prior_run_points]
    pairs.extend(
        (prior_point, structural_point, "structural_oat")
        for prior_point in baseline_prior_points
        for structural_point in non_baseline_structural
    )
    return pairs, {
        "mode": "staged_additive",
        "stage1_prior_points": len(prior_run_points),
        "stage2_baseline_prior_points": len(baseline_prior_points),
        "stage2_structural_points": len(non_baseline_structural),
    }


def _build_prior_run_points(
    *,
    run_cfg: dict,
    targets: list[str],
    outcome_plan: dict,
) -> list[dict]:
    rows: list[dict] = []

    for revenue_per_kpi in outcome_plan["revenue_per_kpi_values"]:
        effective_prior_mode = _resolve_effective_prior_mode(
            run_cfg,
            kpi_type=outcome_plan["kpi_type"],
            revenue_per_kpi=revenue_per_kpi,
        )
        prior_label = _resolve_prior_label(
            effective_prior_mode=effective_prior_mode,
            kpi_type=outcome_plan["kpi_type"],
            revenue_per_kpi=revenue_per_kpi,
        )
        for target_channel in targets:
            roi_grid = _roi_grid_for_target(run_cfg, target_channel)
            if roi_grid is None:
                continue
            baseline_mu, baseline_sigma, baseline_dist = _resolve_roi_baseline_from_grid(
                roi_grid["mu"], roi_grid["sigma"], roi_grid["dist"], run_cfg
            )
            for mu, sigma, dist in product(roi_grid["mu"], roi_grid["sigma"], roi_grid["dist"]):
                roi_overrides = {
                    ch: {
                        "mu": float(baseline_mu),
                        "sigma": float(baseline_sigma),
                        "dist": str(baseline_dist),
                    }
                    for ch in targets
                }
                roi_overrides[target_channel] = {
                    "mu": float(mu),
                    "sigma": float(sigma),
                    "dist": str(dist),
                }
                rows.append(
                    {
                        "target_channel": target_channel,
                        "effective_prior_mode": "roi",
                        "prior_grid_type": "roi",
                        "prior_design_label": prior_label,
                        "revenue_per_kpi": revenue_per_kpi,
                        "kpi_type": outcome_plan["kpi_type"],
                        "kpi_type_effective": "revenue"
                        if (outcome_plan["kpi_type"] == "revenue" or revenue_per_kpi is not None)
                        else "non_revenue",
                        "roi_mu_display": float(mu),
                        "roi_sigma_display": float(sigma),
                        "roi_dist_display": str(dist),
                        "roi_overrides": roi_overrides,
                        "scope_suffix": (
                            f"pmode=roi|rpk={revenue_per_kpi if revenue_per_kpi is not None else 'none'}|"
                            f"target={target_channel}|mu={float(mu):.6f}|sigma={float(sigma):.6f}|dist={str(dist)}"
                        ),
                    }
                )

    return rows


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


def _resolve_roi_baseline_from_grid(
    roi_mu_values: list[float],
    roi_sigma_values: list[float],
    roi_dist_values: list[str],
    run_cfg: dict,
) -> tuple[float, float, str]:
    baseline_cfg = run_cfg.get("baseline", {}) or {}

    baseline_mu_cfg = baseline_cfg.get("roi_mu")
    if baseline_mu_cfg is None:
        baseline_mu = float(roi_mu_values[0])
    else:
        baseline_mu = round(float(baseline_mu_cfg), 6)
        if not _contains_close(roi_mu_values, baseline_mu):
            raise ValueError(
                "Configured baseline.roi_mu is not in the active mu grid. "
                f"baseline.roi_mu={baseline_mu}, active mu grid={roi_mu_values}"
            )

    baseline_sigma_cfg = baseline_cfg.get("roi_sigma")
    if baseline_sigma_cfg is None:
        baseline_sigma = float(roi_sigma_values[0])
    else:
        baseline_sigma = round(float(baseline_sigma_cfg), 6)
        if not _contains_close(roi_sigma_values, baseline_sigma):
            raise ValueError(
                "Configured baseline.roi_sigma is not in the active sigma grid. "
                f"baseline.roi_sigma={baseline_sigma}, active sigma grid={roi_sigma_values}"
            )

    baseline_dist_cfg = baseline_cfg.get("roi_dist")
    if baseline_dist_cfg is None:
        baseline_dist = str(roi_dist_values[0])
    else:
        wanted = str(baseline_dist_cfg).strip().lower()
        mapped = {str(d).strip().lower(): str(d) for d in roi_dist_values}
        if wanted not in mapped:
            raise ValueError(
                "Configured baseline.roi_dist is not in the active dist grid. "
                f"baseline.roi_dist={baseline_dist_cfg}, active dist grid={roi_dist_values}"
            )
        baseline_dist = mapped[wanted]

    return round(float(baseline_mu), 6), round(float(baseline_sigma), 6), str(baseline_dist)


def _resolve_baseline_from_config(cfg, run_cfg: dict) -> tuple[float, float, str]:
    return _resolve_roi_baseline_from_grid(
        [round(float(v), 6) for v in cfg.roi_mu_values],
        [round(float(v), 6) for v in cfg.roi_sigma_values],
        [str(v) for v in cfg.roi_dist_values],
        run_cfg,
    )


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


def _resolve_output_tag(run_cfg: dict, fallback_tag: str) -> str:
    output_cfg = run_cfg.get("output", {}) or {}
    explicit_tag = output_cfg.get("tag")
    if explicit_tag is None or str(explicit_tag).strip().lower() in {"", "null", "none"}:
        return fallback_tag
    return _sanitize_tag_token(str(explicit_tag))


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


def _run_meridian_job(cmd: list[str], *, project_root: str, env: dict) -> dict:
    proc = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, env=env)
    return {
        "returncode": int(proc.returncode),
        "stdout": str(proc.stdout or ""),
        "stderr": str(proc.stderr or ""),
    }


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
    run_mode = str(run_cfg.get("run_mode", "roi_full"))
    parallel_workers = int(run_cfg.get("parallel_workers", 1))
    if os.name == "nt" and parallel_workers > 1:
        print(
            "[warn] Windows + TensorFlow/Meridian multi-process runs may crash with access violations. "
            f"Proceeding with configured parallel_workers={parallel_workers}."
        )
    sweep_type = str((run_cfg.get("sweep", {}) or {}).get("type", "fixed_full_grid"))
    prior_grid_scope = str((run_cfg.get("sweep", {}) or {}).get("prior_grid_scope", "full_grid"))
    structural_grid_scope = str((run_cfg.get("sweep", {}) or {}).get("structural_grid_scope", "full_grid"))
    two_layer_enabled = False

    model_cfg = run_cfg.get("model", {})
    channels = [str(x) for x in model_cfg["channels"]]

    structural_cfg = run_cfg.get("structural", {})
    structural_grids = {
        "alpha_m": _cast_list(structural_cfg.get("alpha_m_values"), [None], cast=float, keep_none=True),
        "ec_m": _cast_list(structural_cfg.get("ec_m_values"), [None], cast=float, keep_none=True),
        "slope_m": _cast_list(structural_cfg.get("slope_m_values"), [1.0], cast=float),
        "max_lag": _cast_list(structural_cfg.get("max_lag_values"), [8], cast=int),
        "adstock_decay": _cast_list(structural_cfg.get("adstock_decay_values"), ["geometric"], lower=True),
    }

    outcome_plan = _resolve_outcome_plan(run_cfg, model_cfg)
    kpi_col = str(outcome_plan["kpi_col"])
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

    if not targets:
        raise ValueError("No targets provided. Pass --targets <channel...> or --channels <channel...>.")

    targets = sorted(str(x) for x in targets)
    targets_tag = "_".join(targets)
    data_tag = _resolve_data_tag(data_csv=data_csv, geo_col=geo_col, explicit_data_tag=explicit_data_tag)
    default_output_tag = f"{targets_tag}__{data_tag}" if data_tag else targets_tag
    output_tag = _resolve_output_tag(run_cfg, default_output_tag)
    targets_str = ",".join(targets)

    run_output_file = str(run_csv_path(output_tag, RUNS_DIR))
    roi_output_file = str(roi_csv_path(output_tag, RUNS_DIR))
    tmp_dir = os.path.dirname(run_output_file)
    os.makedirs(tmp_dir, exist_ok=True)

    prior_run_points = _build_prior_run_points(
        run_cfg=run_cfg,
        targets=targets,
        outcome_plan=outcome_plan,
    )
    prior_run_points_full_count = len(prior_run_points)
    if prior_grid_scope == "baseline_only":
        prior_run_points = _filter_prior_run_points_to_baseline_only(run_cfg, prior_run_points)
    if not prior_run_points:
        raise ValueError("No prior run points were generated. Check prior_mode/outcome settings.")

    channels_json = json.dumps(channels)
    structural_run_points, baseline_structural = _build_structural_run_points(
        structural_grids, structural_grid_scope
    )
    structural_combo_count = len(structural_run_points)
    execution_pairs, execution_plan = _build_execution_pairs(
        run_cfg=run_cfg,
        prior_run_points=prior_run_points,
        structural_run_points=structural_run_points,
        baseline_structural=baseline_structural,
        structural_grid_scope=structural_grid_scope,
    )
    total_runs = len(execution_pairs)

    print(
        "Run plan:",
        f"targets={targets_str}; run_mode={run_mode}; prior_scope={prior_grid_scope}; prior_points={len(prior_run_points)}"
        + (f"/{prior_run_points_full_count}" if prior_grid_scope == "baseline_only" else "")
        + f"; structural_scope={structural_grid_scope}; structural combos={structural_combo_count}; execution={execution_plan['mode']}; total runs={total_runs}",
    )
    print(
        "Outcome mode:",
        f"kpi_col={kpi_col}; kpi_type={outcome_plan['kpi_type']}; "
        f"revenue_per_kpi_values={outcome_plan['revenue_per_kpi_values']}",
    )
    print("Input data CSV =", data_csv)
    print("Run output file =", run_output_file)
    print("ROI output file =", roi_output_file)
    if execution_plan["mode"] == "staged_additive":
        print(
            "Execution mode = staged_additive | "
            f"stage1: {execution_plan['stage1_prior_points']} prior points @ baseline structural; "
            f"stage2: {execution_plan['stage2_baseline_prior_points']} baseline prior point(s) x "
            f"{execution_plan['stage2_structural_points']} non-baseline structural variants; "
            f"parallel_workers={parallel_workers}"
        )
    else:
        print(f"Execution mode = fixed_full_grid | parallel_workers={parallel_workers}")

    has_global_baseline = False
    baseline_mu = baseline_sigma = None
    baseline_dist = None
    baseline_revenue_per_kpi = outcome_plan["revenue_per_kpi"]
    if baseline_revenue_per_kpi is None:
        scenario_values = outcome_plan.get("revenue_per_kpi_values") or []
        if scenario_values:
            baseline_revenue_per_kpi = scenario_values[0]

    baseline_prior_mode = _resolve_effective_prior_mode(
        run_cfg,
        kpi_type=outcome_plan["kpi_type"],
        revenue_per_kpi=baseline_revenue_per_kpi,
    )
    if baseline_prior_mode == "roi":
        roi_grid_cfg = _roi_grid_from_config(run_cfg)
        roi_cfg = build_experiment_config(
            channels=channels,
            roi_mu_values=roi_grid_cfg["mu"],
            roi_sigma_values=roi_grid_cfg["sigma"],
            roi_dist_values=roi_grid_cfg["dist"],
            kpi_col=kpi_col,
            data_csv=data_csv,
            output_file="prior_sensitivity_results.csv",
        )
        baseline_mu, baseline_sigma, baseline_dist = _resolve_baseline_from_config(roi_cfg, run_cfg)
        has_global_baseline = all(v is not None for v in [baseline_mu, baseline_sigma, baseline_dist])

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
    if has_global_baseline:
        print(f"Baseline (effective) = mu={baseline_mu}, sigma={baseline_sigma}, dist={baseline_dist}")
    else:
        print("Baseline (effective) = inferred at summarize stage (no explicit global ROI baseline for this mode)")
    if prior_grid_scope == "baseline_only":
        print("Structural sensitivity Stage 1 = baseline prior only")

    already_done = load_resume_state(run_output_file)

    env = os.environ.copy()
    env["TF_CPP_MIN_LOG_LEVEL"] = "3"
    env["TF_ENABLE_ONEDNN_OPTS"] = "0"

    print(f"Mode = linked target-set | targets={targets_str}")

    run_index = 1
    skipped_runs = 0
    executed_runs = 0
    pending_jobs: list[dict] = []
    grid_iter = iter(execution_pairs)

    for prior_point, structural_point, analysis_stage in grid_iter:
        mu = round(float(prior_point["roi_mu_display"]), 6)
        sigma = round(float(prior_point["roi_sigma_display"]), 6)
        dist = str(prior_point["roi_dist_display"])
        target_channel = str(prior_point.get("target_channel") or targets[0])
        point_roi_grid = _roi_grid_for_target(run_cfg, target_channel)
        if point_roi_grid is None:
            continue
        point_baseline_mu, point_baseline_sigma, point_baseline_dist = _resolve_roi_baseline_from_grid(
            point_roi_grid["mu"],
            point_roi_grid["sigma"],
            point_roi_grid["dist"],
            run_cfg,
        )
        alpha_m = structural_point["alpha_m"]
        alpha_m = None if alpha_m is None else round(float(alpha_m), 6)
        ec_m = structural_point["ec_m"]
        ec_m = None if ec_m is None else round(float(ec_m), 6)
        slope_m = round(float(structural_point["slope_m"]), 6)
        max_lag = int(structural_point["max_lag"])
        adstock_decay = str(structural_point["adstock_decay_spec"]).strip().lower()

        roi_overrides = prior_point["roi_overrides"]
        structural_overrides = {
            "alpha_m": alpha_m,
            "ec_m": ec_m,
            "slope_m": slope_m,
            "max_lag": max_lag,
            "adstock_decay_spec": adstock_decay,
        }
        prior_key = json.dumps(
            {
                "run_mode": run_mode,
                "sweep_type": sweep_type,
                "two_layer_enabled": two_layer_enabled,
                "kpi_type": prior_point["kpi_type"],
                "kpi_type_effective": prior_point["kpi_type_effective"],
                "revenue_per_kpi": prior_point["revenue_per_kpi"],
                "prior_design_mode": prior_point["effective_prior_mode"],
                "prior_grid_type": prior_point["prior_grid_type"],
                "target_channel": target_channel,
                "roi_prior_overrides": roi_overrides,
                "structural_overrides": structural_overrides,
            },
            sort_keys=True,
        )
        scope_key = f"multi|{targets_str}"
        if data_tag:
            scope_key = f"{scope_key}|data={data_tag}"
        scope_key = f"{scope_key}|{prior_point['scope_suffix']}"
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
            skipped_runs += 1
            run_index += 1
            continue

        run_suffix = "_".join(
            [
                output_tag,
                f"r{run_index}",
                target_channel,
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
            "--kpi_type",
            str(prior_point["kpi_type"]),
            "--revenue_per_kpi",
            str(prior_point["revenue_per_kpi"]) if prior_point["revenue_per_kpi"] is not None else "",
            "--time_col",
            time_col,
            "--channels_json",
            channels_json,
            "--target_channel",
            target_channel,
            "--mu",
            str(mu),
            "--sigma",
            str(sigma),
            "--dist",
            dist,
            "--roi_prior_overrides_json",
            json.dumps(roi_overrides, sort_keys=True),
            "--structural_overrides_json",
            json.dumps(structural_overrides, sort_keys=True),
            "--prior_key",
            prior_key,
            "--prior_design_mode",
            str(prior_point["effective_prior_mode"]),
            "--prior_mode_used",
            str(prior_point["effective_prior_mode"]),
            "--prior_grid_type",
            str(prior_point["prior_grid_type"]),
            "--prior_design_label",
            str(prior_point["prior_design_label"]),
            "--run_mode",
            run_mode,
            "--target_channels",
            target_channel,
            "--sweep_type",
            sweep_type,
            "--two_layer_enabled",
            "false",
            "--qc_scope",
            "target_scoped",
            "--qc_target_channels",
            target_channel,
            "--gate_mode",
            "configured" if prior_point["effective_prior_mode"] == "roi" else "auto_from_runs",
            "--data_tag",
            data_tag or Path(data_csv).stem,
            "--out_run_csv",
            tmp_run_out,
            "--out_roi_csv",
            tmp_roi_out,
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
        if prior_point["revenue_per_kpi"] is None:
            # argparse with float does not accept empty string, so pass only when set.
            idx = cmd.index("--revenue_per_kpi")
            del cmd[idx : idx + 2]
        if has_global_baseline:
            cmd.extend([
                "--baseline_mu",
                str(point_baseline_mu),
                "--baseline_sigma",
                str(point_baseline_sigma),
                "--baseline_dist",
                str(point_baseline_dist),
            ])
        if geo_col:
            cmd.extend(["--geo_col", geo_col])
        if population_col:
            cmd.extend(["--population_col", population_col])

        is_baseline_grid_point = (
            _is_baseline_prior_point(run_cfg, prior_point)
            and (
                (alpha_m is None and baseline_structural["alpha_m"] is None)
                or (
                    alpha_m is not None
                    and baseline_structural["alpha_m"] is not None
                    and abs(float(alpha_m) - float(baseline_structural["alpha_m"])) <= 1e-9
                )
            )
            and (
                (ec_m is None and baseline_structural["ec_m"] is None)
                or (
                    ec_m is not None
                    and baseline_structural["ec_m"] is not None
                    and abs(float(ec_m) - float(baseline_structural["ec_m"])) <= 1e-9
                )
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

        pending_jobs.append(
            {
                "analysis_stage": analysis_stage,
                "index": run_index,
                "run_key": run_key,
                "prior_key": prior_key,
                "targets_str": targets_str,
                "target_channel": target_channel,
                "tmp_run_out": tmp_run_out,
                "tmp_roi_out": tmp_roi_out,
                "is_baseline_grid_point": is_baseline_grid_point,
                "cmd": cmd,
                "mu": mu,
                "sigma": sigma,
                "dist": dist,
                "t0": time.time(),
            }
        )
        run_index += 1

    pending_total = len(pending_jobs)
    if pending_total == 0:
        print("No new runs to execute. All runs already exist in output CSVs.")
    else:
        print(f"Executing {pending_total} run(s) with parallel_workers={parallel_workers}...")

    def _finalize_completed_job(job: dict, result: dict, completed_idx: int) -> None:
        nonlocal executed_runs, official_export_done
        if result["returncode"] != 0:
            print("\n--- Subprocess STDOUT ---\n", result["stdout"])
            print("\n--- Subprocess STDERR ---\n", result["stderr"])
            raise RuntimeError(
                f"Subprocess failed with code {result['returncode']} "
                f"(run_index={job['index']}, mu={job['mu']}, sigma={job['sigma']}, dist={job['dist']})"
            )

        ensure_cols = {
            "run_id": job["run_key"],
            "prior_key": job["prior_key"],
            "targets": job["targets_str"],
            "target_channel": job["target_channel"],
            "analysis_stage": job["analysis_stage"],
        }
        append_tmp_to_output(
            tmp_out=job["tmp_run_out"],
            output_file=run_output_file,
            ensure_cols=ensure_cols,
            expected_columns=RUN_OUTPUT_COLUMNS,
            cast_single_target=False,
            normalize_part=True,
        )
        append_tmp_to_output(
            tmp_out=job["tmp_roi_out"],
            output_file=roi_output_file,
            ensure_cols=ensure_cols,
            expected_columns=ROI_OUTPUT_COLUMNS,
            cast_single_target=False,
            normalize_part=False,
        )
        already_done.add(job["run_key"])
        if os.path.exists(job["tmp_run_out"]):
            os.remove(job["tmp_run_out"])
        if os.path.exists(job["tmp_roi_out"]):
            os.remove(job["tmp_roi_out"])
        if job["is_baseline_grid_point"]:
            official_export_done = True

        elapsed_sec = round(time.time() - float(job["t0"]), 2)
        executed_runs += 1
        print(
            f"[done {completed_idx}/{pending_total}] "
            f"run_index={job['index']} mu={job['mu']} sigma={job['sigma']} dist={job['dist']} ({elapsed_sec}s)"
        )

    if pending_total > 0:
        max_workers = max(1, int(parallel_workers))
        if max_workers == 1:
            for completed_idx, job in enumerate(pending_jobs, start=1):
                result = _run_meridian_job(job["cmd"], project_root=project_root, env=env)
                _finalize_completed_job(job, result, completed_idx)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                future_map = {
                    pool.submit(_run_meridian_job, job["cmd"], project_root=project_root, env=env): job
                    for job in pending_jobs
                }
                completed_idx = 0
                for future in as_completed(future_map):
                    completed_idx += 1
                    job = future_map[future]
                    result = future.result()
                    _finalize_completed_job(job, result, completed_idx)

    print("\nALL RUNS COMPLETED.")
    print(f"Run summary: total={total_runs}, executed={executed_runs}, skipped_existing={skipped_runs}")
    print("Saved run diagnostics to:", run_output_file)
    print("Saved ROI results to:", roi_output_file)


if __name__ == "__main__":
    main()
