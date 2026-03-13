import copy
import os
from typing import Any

import yaml


DEFAULT_RUN_CONFIG: dict[str, Any] = {
    "model": {
        "channels": ["meta", "google", "snapchat", "tiktok", "moloco", "liveintent", "beehiiv", "amazon"],
        "kpi_col": "subscriptions",
    },
    "experiment": {
        "multipliers": [0.4, 1.0, 2.0],
        "roi_mu_values": None,
        "roi_sigma_values": None,
        "roi_dist_values": ["Normal", "LogNormal"],
    },
    "defaults": {
        "targets": ["tiktok"],
    },
    "sampler": {
        "n_chains": 4,
        "n_adapt": 700,
        "n_burnin": 500,
        "n_keep": 300,
        "seed": 0,
    },
    "next_grid_policy": {
        "min_dist_pass_rate": 0.7,
        "max_baseline_issue_rate": 0.1,
        "min_param_pass_rate": 0.6,
        "fallback_keep_all_dists": True,
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


def load_run_config(config_path: str | None) -> dict[str, Any]:
    config = copy.deepcopy(DEFAULT_RUN_CONFIG)
    if not config_path:
        return config

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config YAML not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError("Run config YAML must parse to a mapping/object at top-level.")
    return _deep_merge_dict(config, raw)


def dump_run_config(config: dict[str, Any], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False)
