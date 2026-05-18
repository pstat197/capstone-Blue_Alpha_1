from __future__ import annotations

from typing import Any

import yaml

from backend.app.schemas.workflow import ConfigPreview, WorkflowDraft

DEFAULT_MU_VALUES = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
DEFAULT_SIGMA_VALUES = [0.5, 1.0, 1.5]
DEFAULT_DIST_VALUES = ["LogNormal"]


def _list_or_default(raw: Any, default: list[Any]) -> list[Any]:
    if isinstance(raw, list) and raw:
        return raw
    return default


def _normalize_channel_prior_grids(
    raw: Any,
    channels: list[str],
    *,
    default_mu_values: list[Any],
    default_sigma_values: list[Any],
    default_dist_values: list[Any],
) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        raw = {}

    normalized: dict[str, dict[str, Any]] = {}
    for channel in channels:
        channel_raw = raw.get(channel)
        if not isinstance(channel_raw, dict):
            channel_raw = {}

        enabled = bool(channel_raw.get("enabled", True))
        use_custom = bool(channel_raw.get("use_custom", channel_raw.get("custom", False)))
        mu_values = _list_or_default(
            channel_raw.get("roi_mu_values") or channel_raw.get("mu_values"),
            default_mu_values,
        )
        sigma_values = _list_or_default(
            channel_raw.get("roi_sigma_values") or channel_raw.get("sigma_values"),
            default_sigma_values,
        )
        dist_values = _list_or_default(
            channel_raw.get("roi_dist_values") or channel_raw.get("distributions"),
            default_dist_values,
        )
        normalized[channel] = {
            "enabled": enabled,
            "use_custom": use_custom,
            "roi_mu_values": mu_values if use_custom else default_mu_values,
            "roi_sigma_values": sigma_values if use_custom else default_sigma_values,
            "roi_dist_values": dist_values if use_custom else default_dist_values,
        }
    return normalized


def _estimate_run_count(config: dict[str, Any]) -> int:
    active = config["run_modes"][config["run_mode"]]
    channel_grids = active.get("channel_prior_grids")
    if isinstance(channel_grids, dict) and channel_grids:
        total = 0
        for channel in config["model"]["channels"]:
            grid = channel_grids.get(channel)
            if not isinstance(grid, dict) or not grid.get("enabled", True):
                continue
            total += (
                len(grid.get("roi_mu_values", []))
                * len(grid.get("roi_sigma_values", []))
                * len(grid.get("roi_dist_values", []))
            )
        return total
    channels = config["model"]["channels"]
    return len(channels) * len(active["roi_mu_values"]) * len(active["roi_sigma_values"]) * len(active["roi_dist_values"])


def build_config_preview(draft: WorkflowDraft) -> ConfigPreview:
    column_mapping = draft.column_mapping or {}
    outcome = draft.outcome or {}
    prior_grid = draft.prior_grid or {}
    structural = draft.structural or {}
    sampler = draft.sampler or {}
    dataset = draft.dataset or {}

    channels = _list_or_default(column_mapping.get("channels") or dataset.get("channels"), [])
    mu_values = _list_or_default(prior_grid.get("roi_mu_values") or prior_grid.get("mu_values"), DEFAULT_MU_VALUES)
    sigma_values = _list_or_default(prior_grid.get("roi_sigma_values") or prior_grid.get("sigma_values"), DEFAULT_SIGMA_VALUES)
    dist_values = _list_or_default(prior_grid.get("roi_dist_values") or prior_grid.get("distributions"), DEFAULT_DIST_VALUES)
    channel_prior_grids = _normalize_channel_prior_grids(
        prior_grid.get("channel_prior_grids"),
        channels,
        default_mu_values=mu_values,
        default_sigma_values=sigma_values,
        default_dist_values=dist_values,
    )
    active_channels = [channel for channel in channels if channel_prior_grids[channel]["enabled"]]

    normalized_config: dict[str, Any] = {
        "run_mode": "roi_full",
        "parallel_workers": int(sampler.get("parallel_workers", 4)),
        "model": {
            "data_csv": dataset.get("data_csv") or dataset.get("path"),
            "channels": channels,
            "time_col": column_mapping.get("time_col"),
            "geo_col": column_mapping.get("geo_col"),
            "population_col": column_mapping.get("population_col"),
        },
        "outcome": {
            "kpi_col": outcome.get("kpi_col") or column_mapping.get("kpi_col"),
            "kpi_type": outcome.get("kpi_type", "non_revenue"),
            "roi_mode": outcome.get("roi_mode"),
            "revenue_col": outcome.get("revenue_col"),
            "revenue_per_kpi": outcome.get("revenue_per_kpi"),
        },
        "prior_mode": "roi",
        "run_modes": {
            "roi_full": {
                "roi_mu_values": mu_values,
                "roi_sigma_values": sigma_values,
                "roi_dist_values": dist_values,
                "channel_prior_grids": channel_prior_grids,
                "n_chains": int(sampler.get("n_chains", 4)),
                "n_adapt": int(sampler.get("n_adapt", 700)),
                "n_burnin": int(sampler.get("n_burnin", 500)),
                "n_keep": int(sampler.get("n_keep", 300)),
            }
        },
        "defaults": {
            "targets": active_channels,
            "target_sets": None,
        },
        "structural": {
            "alpha_m_values": _list_or_default(structural.get("alpha_m_values"), [0.3]),
            "ec_m_values": _list_or_default(structural.get("ec_m_values"), [0.5]),
            "slope_m_values": _list_or_default(structural.get("slope_m_values"), [1.2]),
            "max_lag_values": _list_or_default(structural.get("max_lag_values"), [4]),
            "adstock_decay_values": _list_or_default(structural.get("adstock_decay_values"), ["geometric"]),
        },
        "sampler": {
            "n_chains": int(sampler.get("n_chains", 4)),
            "n_adapt": int(sampler.get("n_adapt", 700)),
            "n_burnin": int(sampler.get("n_burnin", 500)),
            "n_keep": int(sampler.get("n_keep", 300)),
            "seed": int(sampler.get("seed", 0)),
        },
        "sweep": {
            "type": "fixed_full_grid",
            "prior_grid_scope": "full_grid",
            "structural_grid_scope": "full_grid",
            "allow_reduced_prior_grid": any(grid["use_custom"] for grid in channel_prior_grids.values()),
        },
    }
    estimated_run_count = _estimate_run_count(normalized_config)

    warnings: list[str] = []
    errors: list[str] = []
    if not normalized_config["model"].get("data_csv"):
        errors.append("Dataset CSV is required.")
    if not normalized_config["model"].get("time_col"):
        errors.append("Time column is required.")
    if not normalized_config["outcome"].get("kpi_col"):
        errors.append("KPI column is required.")
    if normalized_config["outcome"]["kpi_type"] == "non_revenue" and not normalized_config["outcome"].get("revenue_per_kpi"):
        errors.append("Non-revenue KPI requires outcome.revenue_per_kpi for revenue-equivalent ROI.")
    if not active_channels:
        errors.append("At least one active channel is required.")
    if estimated_run_count > 0:
        warnings.append("Preview only: Phase 3 does not launch Meridian or write sensitivity.yaml.")

    return ConfigPreview(
        workflow_id=draft.workflow_id,
        yaml=yaml.safe_dump(normalized_config, sort_keys=False),
        estimated_run_count=estimated_run_count,
        warnings=warnings,
        errors=errors,
        normalized_config=normalized_config,
    )
