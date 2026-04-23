import copy
import os
from typing import Any

import yaml


DEFAULT_RUN_CONFIG: dict[str, Any] = {
    "model": {
        "channels": ["meta", "google", "snapchat", "tiktok", "moloco", "liveintent", "beehiiv", "amazon"],
        "data_csv": "data/raw/monthly_mocha.csv",
        "data_tag": None,
        "kpi_col": "subscriptions",
        "time_col": "date",
        "geo_col": None,
        "population_col": None,
    },
    "experiment": {
        # Explicit-prior mode only: grid values must be provided directly.
        "roi_mu_values": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
        "roi_sigma_values": [1.0, 1.5, 2.0],
        "roi_dist_values": ["LogNormal"],
    },
    "structural": {
        # Fixed structural defaults unless explicitly overridden.
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
        # Optional explicit baseline. When null, baseline defaults to first value in each active grid.
        "roi_mu": None,
        "roi_sigma": None,
        "roi_dist": None,
    },
    "sampler": {
        "n_chains": 4,
        "n_adapt": 700,
        "n_burnin": 500,
        "n_keep": 300,
        "seed": 0,
    },
    "two_layer": {
        "enabled": True,
        "clean_between_layers": True,
        "layer1": {
            "roi_mu_values": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
            "roi_sigma_values": [1.0, 1.5, 2.0],
            "roi_dist_values": ["LogNormal"],
        },
        "layer2": {
            "mode": "auto_refine",
            "top_n_mu": 3,
            "top_n_sigma": 2,
            "mu_step": 0.25,
            "sigma_step": 0.25,
            "fallback": {
                "roi_mu_values": [0.5, 1.0, 1.5, 2.0],
                "roi_sigma_values": [1.0, 1.5],
                "roi_dist_values": ["LogNormal"],
            },
        },
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
    if isinstance(raw, list):
        items = raw
    else:
        items = [raw]
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
    if isinstance(raw, list):
        items = raw
    else:
        items = [raw]
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


def _validate_and_normalize_config(config: dict[str, Any]) -> dict[str, Any]:
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

    kpi_col = model.get("kpi_col", "subscriptions")
    if kpi_col is None or str(kpi_col).strip() == "":
        raise ValueError("Config field 'model.kpi_col' cannot be empty.")
    model["kpi_col"] = str(kpi_col).strip()

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

    exp = config.setdefault("experiment", {})

    raw_mu = exp.get("roi_mu_values")
    mu_values = _as_numeric_list(raw_mu, "experiment.roi_mu_values")
    if not mu_values:
        raise ValueError("Config field 'experiment.roi_mu_values' must contain at least one value.")
    exp["roi_mu_values"] = [round(float(v), 6) for v in mu_values]

    raw_sigma = exp.get("roi_sigma_values")
    sigma_values = _as_numeric_list(raw_sigma, "experiment.roi_sigma_values")
    if not sigma_values:
        raise ValueError("Config field 'experiment.roi_sigma_values' must contain at least one value.")
    if any(v <= 0 for v in sigma_values):
        raise ValueError("Config field 'experiment.roi_sigma_values' must be strictly positive.")
    exp["roi_sigma_values"] = [round(float(v), 6) for v in sigma_values]

    dist_values = _as_string_list(exp.get("roi_dist_values"), "experiment.roi_dist_values")
    if not dist_values:
        raise ValueError("Config field 'experiment.roi_dist_values' must contain at least one value.")
    exp["roi_dist_values"] = _dedupe_preserve_order(dist_values)

    baseline = config.setdefault("baseline", {})
    for baseline_key in ["roi_mu", "roi_sigma"]:
        raw = baseline.get(baseline_key)
        if raw is None or str(raw).strip().lower() == "null":
            baseline[baseline_key] = None
            continue
        try:
            baseline[baseline_key] = round(float(raw), 6)
        except Exception as exc:
            raise ValueError(f"Config field 'baseline.{baseline_key}' must be numeric or null.") from exc
    if baseline["roi_sigma"] is not None and baseline["roi_sigma"] <= 0:
        raise ValueError("Config field 'baseline.roi_sigma' must be strictly positive when provided.")

    raw_dist = baseline.get("roi_dist")
    if raw_dist is None or str(raw_dist).strip().lower() == "null":
        baseline["roi_dist"] = None
    else:
        baseline["roi_dist"] = str(raw_dist).strip()
        if baseline["roi_dist"] == "":
            raise ValueError("Config field 'baseline.roi_dist' cannot be empty.")

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
            channels = _as_string_list(item, item_field)
            channels = _dedupe_preserve_order(channels)
            if not channels:
                raise ValueError(f"Config field '{item_field}' cannot be empty.")
            key = tuple(sorted(channels))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unknown_set_targets = [t for t in channels if t not in model_channel_set]
            if unknown_set_targets:
                raise ValueError(
                    f"Config field '{item_field}' has channels not present in model.channels: "
                    + ", ".join(unknown_set_targets)
                )
            normalized_sets.append(channels)
        if not normalized_sets:
            raise ValueError("Config field 'defaults.target_sets' must contain at least one non-empty channel set.")
        defaults["target_sets"] = normalized_sets

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
