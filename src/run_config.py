from __future__ import annotations

import copy
import os
from typing import Any

import yaml

ROI_PRIOR_POLICY_ERROR = (
    "ROI prior mode for non-revenue KPI requires outcome.revenue_per_kpi. "
    "Please add a business-defined revenue_per_kpi value to config/sensitivity.yaml "
    "to run revenue-equivalent ROI analysis."
)

FIXED_ROI_MU_VALUES = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
FIXED_ROI_SIGMA_VALUES = [0.5, 1.0, 1.5]
FIXED_ROI_DIST_VALUES = ["LogNormal"]
CONTRIBUTION_PRIOR_MODE = "contribution"


DEFAULT_RUN_CONFIG: dict[str, Any] = {
    "run_mode": "roi_full",
    "parallel_workers": 4,
    "run_modes": {
        "roi_full": {
            "roi_mu_values": FIXED_ROI_MU_VALUES,
            "roi_sigma_values": FIXED_ROI_SIGMA_VALUES,
            "roi_dist_values": ["LogNormal"],
            "n_chains": 4,
            "n_adapt": 700,
            "n_burnin": 500,
            "n_keep": 300,
        },
    },
    "model": {
        "channels": ["meta", "google", "snapchat", "tiktok", "moloco", "liveintent", "beehiiv", "amazon"],
        "data_csv": "data/raw/monthly_mocha.csv",
        "data_tag": None,
        "kpi_col": "subscriptions",
        "time_col": "date",
        "geo_col": None,
        "population_col": None,
    },
    "outcome": {
        "kpi_col": "subscriptions",
        "kpi_type": "non_revenue",  # auto | revenue | non_revenue
        "revenue_per_kpi": None,
        "revenue_per_kpi_values": None,
    },
    "prior_mode": "roi",
    # Backward-compatible materialized ROI grid used by existing internals.
    "experiment": {
        "roi_mu_values": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
        "roi_sigma_values": [1.0, 1.5, 2.0],
        "roi_dist_values": ["LogNormal"],
    },
    "structural": {
        "alpha_m_values": [None],
        "ec_m_values": [None],
        "slope_m_values": [1.0],
        "max_lag_values": [8],
        "adstock_decay_values": ["geometric"],
    },
    "defaults": {
        "targets": ["tiktok"],
        "target_sets": None,
    },
    "baseline": {
        "roi_mu": None,
        "roi_sigma": None,
        "roi_dist": None,
    },
    "sweep": {
        "type": "fixed_full_grid",
        "prior_grid_scope": "full_grid",
        "structural_grid_scope": "full_grid",
    },
    "sampler": {
        "n_chains": 4,
        "n_adapt": 700,
        "n_burnin": 500,
        "n_keep": 300,
        "seed": 0,
    },
}


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge_dict(out[k], v)
        else:
            out[k] = v
    return out


def _as_numeric_list(raw: Any, field_name: str) -> list[float]:
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out = []
    for idx, v in enumerate(items):
        try:
            out.append(float(v))
        except Exception as exc:
            raise ValueError(f"Config field '{field_name}[{idx}]' must be numeric; got {v!r}.") from exc
    return out


def _as_string_list(raw: Any, field_name: str) -> list[str]:
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out = []
    for idx, v in enumerate(items):
        s = str(v).strip()
        if not s:
            raise ValueError(f"Config field '{field_name}[{idx}]' cannot be empty.")
        out.append(s)
    return out


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _require_fixed_roi_prior_grid(active_profile: dict[str, Any]) -> None:
    mu_values = [round(float(v), 6) for v in active_profile.get("roi_mu_values", [])]
    sigma_values = [round(float(v), 6) for v in active_profile.get("roi_sigma_values", [])]
    dist_values = [str(v) for v in active_profile.get("roi_dist_values", [])]
    if (
        mu_values != FIXED_ROI_MU_VALUES
        or sigma_values != FIXED_ROI_SIGMA_VALUES
        or dist_values != FIXED_ROI_DIST_VALUES
    ):
        raise ValueError(
            "This one-channel prior sensitivity workflow requires the fixed ROI prior grid: "
            f"roi_mu_values={FIXED_ROI_MU_VALUES}, "
            f"roi_sigma_values={FIXED_ROI_SIGMA_VALUES}, "
            f"roi_dist_values={FIXED_ROI_DIST_VALUES}."
        )


def _as_optional_float(raw: Any, field_name: str) -> float | None:
    if raw is None or str(raw).strip().lower() in {"", "null", "none", "nan"}:
        return None
    try:
        return float(raw)
    except Exception as exc:
        raise ValueError(f"Config field '{field_name}' must be numeric or null.") from exc


def _normalize_positive_list(values: list[float], field_name: str) -> list[float]:
    rounded = [round(float(v), 6) for v in values]
    if any(v <= 0 for v in rounded):
        raise ValueError(f"Config field '{field_name}' must contain strictly positive values.")
    return rounded


def _normalize_run_mode_profile(name: str, raw_profile: Any) -> dict[str, Any]:
    if not isinstance(raw_profile, dict):
        raise ValueError(f"Config field 'run_modes.{name}' must be a mapping/object.")

    mu_values = _as_numeric_list(raw_profile.get("roi_mu_values"), f"run_modes.{name}.roi_mu_values")
    if not mu_values:
        raise ValueError(f"Config field 'run_modes.{name}.roi_mu_values' must contain at least one value.")
    mu_values = _normalize_positive_list(mu_values, f"run_modes.{name}.roi_mu_values")

    sigma_values = _as_numeric_list(raw_profile.get("roi_sigma_values"), f"run_modes.{name}.roi_sigma_values")
    if not sigma_values:
        raise ValueError(f"Config field 'run_modes.{name}.roi_sigma_values' must contain at least one value.")
    sigma_values = _normalize_positive_list(sigma_values, f"run_modes.{name}.roi_sigma_values")

    dist_values = _as_string_list(raw_profile.get("roi_dist_values", ["LogNormal"]), f"run_modes.{name}.roi_dist_values")
    if not dist_values:
        raise ValueError(f"Config field 'run_modes.{name}.roi_dist_values' must contain at least one value.")
    dist_values = _dedupe_preserve_order(dist_values)

    sampler_out: dict[str, int] = {}
    for sampler_key in ["n_chains", "n_adapt", "n_burnin", "n_keep"]:
        try:
            sampler_out[sampler_key] = int(raw_profile.get(sampler_key))
        except Exception as exc:
            raise ValueError(f"Config field 'run_modes.{name}.{sampler_key}' must be an integer.") from exc
    if sampler_out["n_chains"] <= 0 or sampler_out["n_keep"] <= 0:
        raise ValueError(f"Config field 'run_modes.{name}' requires n_chains>0 and n_keep>0.")
    if sampler_out["n_adapt"] < 0 or sampler_out["n_burnin"] < 0:
        raise ValueError(f"Config field 'run_modes.{name}' requires n_adapt>=0 and n_burnin>=0.")

    return {
        "roi_mu_values": mu_values,
        "roi_sigma_values": sigma_values,
        "roi_dist_values": dist_values,
        **sampler_out,
    }


def _normalize_structural(config: dict[str, Any]) -> None:
    structural = config.setdefault("structural", {})

    alpha_values = structural.get("alpha_m_values", [None])
    if alpha_values is None:
        alpha_values = [None]
    if not isinstance(alpha_values, list):
        alpha_values = [alpha_values]
    normalized_alpha = []
    for idx, v in enumerate(alpha_values):
        if v is None or str(v).strip().lower() in {"", "null", "none"}:
            normalized_alpha.append(None)
        else:
            try:
                fv = float(v)
            except Exception as exc:
                raise ValueError(f"Config field 'structural.alpha_m_values[{idx}]' must be numeric or null.") from exc
            if fv < 0 or fv > 1:
                raise ValueError("Config field 'structural.alpha_m_values' must be in [0, 1].")
            normalized_alpha.append(round(fv, 6))
    structural["alpha_m_values"] = normalized_alpha or [None]

    ec_values = structural.get("ec_m_values", [None])
    if ec_values is None:
        ec_values = [None]
    if not isinstance(ec_values, list):
        ec_values = [ec_values]
    normalized_ec = []
    for idx, v in enumerate(ec_values):
        if v is None or str(v).strip().lower() in {"", "null", "none"}:
            normalized_ec.append(None)
        else:
            try:
                fv = float(v)
            except Exception as exc:
                raise ValueError(f"Config field 'structural.ec_m_values[{idx}]' must be numeric or null.") from exc
            if fv <= 0:
                raise ValueError("Config field 'structural.ec_m_values' must be > 0 when provided.")
            normalized_ec.append(round(fv, 6))
    structural["ec_m_values"] = normalized_ec or [None]

    slope_values = _as_numeric_list(structural.get("slope_m_values", [1.0]), "structural.slope_m_values")
    if not slope_values:
        slope_values = [1.0]
    if any(v <= 0 for v in slope_values):
        raise ValueError("Config field 'structural.slope_m_values' must be > 0.")
    structural["slope_m_values"] = [round(float(v), 6) for v in slope_values]

    lag_values = _as_numeric_list(structural.get("max_lag_values", [8]), "structural.max_lag_values")
    if not lag_values:
        lag_values = [8]
    if any(int(v) < 0 for v in lag_values):
        raise ValueError("Config field 'structural.max_lag_values' must be >= 0.")
    structural["max_lag_values"] = [int(v) for v in lag_values]

    decay_values = _as_string_list(structural.get("adstock_decay_values", ["geometric"]), "structural.adstock_decay_values")
    if not decay_values:
        decay_values = ["geometric"]
    normalized_decay = [str(v).strip().lower() for v in decay_values]
    allowed = {"geometric", "binomial"}
    unknown = [v for v in normalized_decay if v not in allowed]
    if unknown:
        raise ValueError(f"Config field 'structural.adstock_decay_values' has unsupported values: {unknown}")
    structural["adstock_decay_values"] = _dedupe_preserve_order(normalized_decay)


def _validate_and_normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    run_mode = str(config.get("run_mode", DEFAULT_RUN_CONFIG["run_mode"])).strip().lower()
    if not run_mode:
        run_mode = str(DEFAULT_RUN_CONFIG["run_mode"])
    config["run_mode"] = run_mode

    try:
        parallel_workers = int(config.get("parallel_workers", DEFAULT_RUN_CONFIG["parallel_workers"]))
    except Exception as exc:
        raise ValueError("Config field 'parallel_workers' must be an integer.") from exc
    if parallel_workers <= 0:
        raise ValueError("Config field 'parallel_workers' must be > 0.")
    config["parallel_workers"] = parallel_workers

    raw_run_modes = config.get("run_modes")
    if not isinstance(raw_run_modes, dict) or not raw_run_modes:
        raise ValueError("Config field 'run_modes' must be a non-empty mapping/object.")
    normalized_run_modes: dict[str, dict[str, Any]] = {}
    for mode_name, raw_profile in raw_run_modes.items():
        mode_key = str(mode_name).strip().lower()
        if not mode_key:
            raise ValueError("Config field 'run_modes' contains an empty mode name.")
        normalized_run_modes[mode_key] = _normalize_run_mode_profile(mode_key, raw_profile)
    if run_mode not in normalized_run_modes:
        raise ValueError(
            "Config field 'run_mode' must be one of: " + ", ".join(sorted(normalized_run_modes.keys()))
        )
    config["run_modes"] = normalized_run_modes

    active_profile = normalized_run_modes[run_mode]

    model = config.setdefault("model", {})
    channels = _as_string_list(model.get("channels"), "model.channels")
    if not channels:
        raise ValueError("Config field 'model.channels' must contain at least one channel.")
    model["channels"] = _dedupe_preserve_order(channels)
    model_channel_set = set(model["channels"])

    data_csv = model.get("data_csv")
    if data_csv is None or str(data_csv).strip() == "":
        raise ValueError("Config field 'model.data_csv' is required.")
    model["data_csv"] = str(data_csv).strip()

    data_tag = model.get("data_tag")
    if data_tag is None or str(data_tag).strip().lower() in {"", "null", "none"}:
        model["data_tag"] = None
    else:
        model["data_tag"] = str(data_tag).strip()

    time_col = model.get("time_col", "date")
    if time_col is None or str(time_col).strip() == "":
        raise ValueError("Config field 'model.time_col' cannot be empty.")
    model["time_col"] = str(time_col).strip()

    geo_col = model.get("geo_col")
    if geo_col is None or str(geo_col).strip().lower() in {"", "null", "none"}:
        model["geo_col"] = None
    else:
        model["geo_col"] = str(geo_col).strip()

    population_col = model.get("population_col")
    if population_col is None or str(population_col).strip().lower() in {"", "null", "none"}:
        model["population_col"] = None
    else:
        model["population_col"] = str(population_col).strip()

    outcome = config.setdefault("outcome", {})
    kpi_col = str(outcome.get("kpi_col") or model.get("kpi_col") or "subscriptions").strip()
    if not kpi_col:
        raise ValueError("Config field 'outcome.kpi_col' cannot be empty.")
    outcome["kpi_col"] = kpi_col
    model["kpi_col"] = kpi_col  # Keep legacy consumers in sync.

    kpi_type = str(outcome.get("kpi_type", "auto")).strip().lower()
    if kpi_type not in {"auto", "revenue", "non_revenue"}:
        raise ValueError("Config field 'outcome.kpi_type' must be one of: auto, revenue, non_revenue.")
    outcome["kpi_type"] = kpi_type

    revenue_per_kpi = _as_optional_float(outcome.get("revenue_per_kpi"), "outcome.revenue_per_kpi")
    if revenue_per_kpi is not None and revenue_per_kpi <= 0:
        raise ValueError("Config field 'outcome.revenue_per_kpi' must be > 0 when provided.")
    outcome["revenue_per_kpi"] = None if revenue_per_kpi is None else round(float(revenue_per_kpi), 6)

    rpk_values = _as_numeric_list(outcome.get("revenue_per_kpi_values"), "outcome.revenue_per_kpi_values")
    if rpk_values:
        rpk_values = _normalize_positive_list(rpk_values, "outcome.revenue_per_kpi_values")
        if outcome["revenue_per_kpi"] is not None:
            if not any(abs(v - outcome["revenue_per_kpi"]) <= 1e-9 for v in rpk_values):
                rpk_values = [outcome["revenue_per_kpi"], *rpk_values]
        outcome["revenue_per_kpi_values"] = _dedupe_preserve_order([str(v) for v in rpk_values])
        outcome["revenue_per_kpi_values"] = [round(float(v), 6) for v in outcome["revenue_per_kpi_values"]]
    else:
        outcome["revenue_per_kpi_values"] = None

    legacy_prior_design = config.get("prior_design", {}) or {}
    if legacy_prior_design and not isinstance(legacy_prior_design, dict):
        raise ValueError("Config field 'prior_design' must be a mapping/object when provided.")
    legacy_prior_mode = str(legacy_prior_design.get("mode", "")).strip().lower()
    if legacy_prior_mode == CONTRIBUTION_PRIOR_MODE:
        raise ValueError("This one-channel prior sensitivity workflow is ROI-prior only; contribution prior mode is not supported.")

    prior_mode = str(config.get("prior_mode", legacy_prior_design.get("mode", "roi"))).strip().lower()
    if prior_mode == CONTRIBUTION_PRIOR_MODE:
        raise ValueError("This one-channel prior sensitivity workflow is ROI-prior only; contribution prior mode is not supported.")
    if prior_mode not in {"auto", "roi"}:
        raise ValueError("Config field 'prior_mode' must be one of: auto, roi.")
    if kpi_type == "non_revenue" and outcome["revenue_per_kpi"] is None:
        raise ValueError(ROI_PRIOR_POLICY_ERROR)
    _require_fixed_roi_prior_grid(active_profile)
    config["prior_mode"] = "roi"
    config.pop("prior_design", None)

    config["active_prior_grids"] = {
        "roi": {
            "roi_mu_values": list(active_profile["roi_mu_values"]),
            "roi_sigma_values": list(active_profile["roi_sigma_values"]),
            "roi_dist_values": list(active_profile["roi_dist_values"]),
        },
    }

    # Keep legacy experiment block synchronized with the active run_mode ROI grid.
    exp = config.setdefault("experiment", {})
    exp["roi_mu_values"] = list(config["active_prior_grids"]["roi"]["roi_mu_values"])
    exp["roi_sigma_values"] = list(config["active_prior_grids"]["roi"]["roi_sigma_values"])
    exp["roi_dist_values"] = list(config["active_prior_grids"]["roi"]["roi_dist_values"])

    baseline = config.setdefault("baseline", {})
    for baseline_key in ["roi_mu", "roi_sigma"]:
        baseline[baseline_key] = _as_optional_float(baseline.get(baseline_key), f"baseline.{baseline_key}")
    if baseline["roi_sigma"] is not None and baseline["roi_sigma"] <= 0:
        raise ValueError("Config field 'baseline.roi_sigma' must be > 0 when provided.")

    raw_dist = baseline.get("roi_dist")
    if raw_dist is None or str(raw_dist).strip().lower() in {"", "null", "none"}:
        baseline["roi_dist"] = None
    else:
        baseline["roi_dist"] = str(raw_dist).strip()

    defaults = config.setdefault("defaults", {})
    targets = _as_string_list(defaults.get("targets", ["tiktok"]), "defaults.targets")
    if not targets:
        raise ValueError("Config field 'defaults.targets' must contain at least one channel.")
    defaults["targets"] = _dedupe_preserve_order(targets)
    unknown_default_targets = [t for t in defaults["targets"] if t not in model_channel_set]
    if unknown_default_targets:
        raise ValueError(
            "Config field 'defaults.targets' has channels not present in model.channels: "
            + ", ".join(unknown_default_targets)
        )

    raw_target_sets = defaults.get("target_sets")
    if raw_target_sets is None or str(raw_target_sets).strip().lower() in {"", "null", "none"}:
        defaults["target_sets"] = None
    else:
        if not isinstance(raw_target_sets, list):
            raise ValueError("Config field 'defaults.target_sets' must be a list of channel lists.")
        normalized_sets: list[list[str]] = []
        seen_keys: set[tuple[str, ...]] = set()
        for idx, item in enumerate(raw_target_sets):
            item_field = f"defaults.target_sets[{idx}]"
            set_channels = _dedupe_preserve_order(_as_string_list(item, item_field))
            if not set_channels:
                raise ValueError(f"Config field '{item_field}' cannot be empty.")
            key = tuple(sorted(set_channels))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unknown_set_targets = [t for t in set_channels if t not in model_channel_set]
            if unknown_set_targets:
                raise ValueError(
                    f"Config field '{item_field}' has channels not present in model.channels: "
                    + ", ".join(unknown_set_targets)
                )
            normalized_sets.append(set_channels)
        defaults["target_sets"] = normalized_sets or None

    sweep = config.setdefault("sweep", {})
    sweep_type = str(sweep.get("type", "fixed_full_grid")).strip().lower()
    if sweep_type not in {"fixed_full_grid"}:
        raise ValueError("Config field 'sweep.type' currently supports only: fixed_full_grid.")
    sweep["type"] = sweep_type
    prior_grid_scope = str(sweep.get("prior_grid_scope", "full_grid")).strip().lower()
    if prior_grid_scope not in {"full_grid", "baseline_only"}:
        raise ValueError("Config field 'sweep.prior_grid_scope' must be one of: full_grid, baseline_only.")
    sweep["prior_grid_scope"] = prior_grid_scope
    structural_grid_scope = str(sweep.get("structural_grid_scope", "full_grid")).strip().lower()
    if structural_grid_scope not in {"full_grid", "one_at_a_time"}:
        raise ValueError(
            "Config field 'sweep.structural_grid_scope' must be one of: full_grid, one_at_a_time."
        )
    sweep["structural_grid_scope"] = structural_grid_scope
    # Fixed full-grid is now the only supported workflow path.
    if "enable_two_layer" in sweep:
        sweep.pop("enable_two_layer", None)
    config.pop("two_layer", None)

    _normalize_structural(config)

    sampler = config.setdefault("sampler", {})
    for key in ["n_chains", "n_adapt", "n_burnin", "n_keep"]:
        sampler[key] = int(active_profile[key])
    for key in ["n_chains", "n_adapt", "n_burnin", "n_keep", "seed"]:
        raw = sampler.get(key, DEFAULT_RUN_CONFIG["sampler"][key])
        try:
            sampler[key] = int(raw)
        except Exception as exc:
            raise ValueError(f"Config field 'sampler.{key}' must be an integer.") from exc
    if sampler["n_chains"] <= 0 or sampler["n_keep"] <= 0:
        raise ValueError("Config fields 'sampler.n_chains' and 'sampler.n_keep' must be > 0.")
    if sampler["n_adapt"] < 0 or sampler["n_burnin"] < 0:
        raise ValueError("Config fields 'sampler.n_adapt' and 'sampler.n_burnin' must be >= 0.")

    return config


def load_run_config(config_path: str | None) -> dict[str, Any]:
    config = copy.deepcopy(DEFAULT_RUN_CONFIG)
    if not config_path:
        return _validate_and_normalize_config(config)

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config YAML not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError("Run config YAML must parse to a mapping/object at top-level.")

    merged = _deep_merge_dict(config, raw)
    return _validate_and_normalize_config(merged)


def dump_run_config(config: dict[str, Any], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False)
