from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_PRIMARY_DIST = "LogNormal"


def _safe_float(value: object) -> float | None:
    try:
        out = float(value)
        if np.isnan(out):
            return None
        return out
    except Exception:
        return None


def _normalize_dist(value: object) -> str:
    return str(value or "").strip().lower()


def _sorted_numeric(values: pd.Series) -> list[float]:
    numeric = pd.to_numeric(values, errors="coerce").dropna().astype(float)
    if numeric.empty:
        return []
    return sorted(numeric.unique().tolist())


def _decode_token_float(token: object) -> float | None:
    if token is None:
        return None
    cleaned = str(token).strip()
    if not cleaned:
        return None
    cleaned = "".join(ch for ch in cleaned if ch.isdigit() or ch in {".", "p", "+", "-"})
    if not cleaned:
        return None
    normalized = cleaned.replace("p", ".").replace("P", ".")
    try:
        out = float(normalized)
    except Exception:
        return None
    if np.isnan(out):
        return None
    return out


def _decode_token_int(token: object) -> int | None:
    val = _decode_token_float(token)
    if val is None:
        return None
    return max(1, int(round(val)))


def _parse_structural_from_run_id(run_id: object) -> dict[str, object]:
    txt = str(run_id or "")
    if not txt:
        return {}
    parts = txt.split("|")

    def pull(name: str) -> str | None:
        prefix = f"{name.lower()}="
        for token in parts:
            raw = str(token or "")
            if raw.lower().startswith(prefix):
                idx = raw.find("=")
                return raw[idx + 1 :] if idx >= 0 else None
        return None

    alpha = _decode_token_float(pull("alpha"))
    ec = _decode_token_float(pull("ec"))
    slope = _decode_token_float(pull("slope"))
    lag = _decode_token_int(pull("lag"))
    decay = pull("decay")

    out: dict[str, object] = {}
    if alpha is not None:
        out["adstock_alpha_m"] = alpha
    if ec is not None:
        out["saturation_ec_m"] = ec
    if slope is not None:
        out["saturation_slope_m"] = slope
    if lag is not None:
        out["max_lag"] = lag
    if decay:
        out["adstock_decay_spec"] = str(decay).strip().lower()
    return out


def _col_series(df: pd.DataFrame, col: str, default: object = np.nan) -> pd.Series:
    if col in df.columns:
        return df[col]
    return pd.Series([default] * len(df), index=df.index)


def _pick_contribution_cols(df: pd.DataFrame) -> tuple[str | None, str | None, str]:
    contribution_candidates = [
        "incremental_value_new",
        "incremental_outcome_new",
        "delta_value",
        "delta_outcome",
    ]
    contribution_delta_candidates = [
        "delta_value",
        "delta_outcome",
        "delta_abs",
    ]

    contribution_col = next((c for c in contribution_candidates if c in df.columns), None)
    contribution_delta_col = next((c for c in contribution_delta_candidates if c in df.columns), None)

    if contribution_col is None:
        note = "no contribution column found"
    else:
        note = f"using contribution column '{contribution_col}'"

    return contribution_col, contribution_delta_col, note


def resolve_workbench_dist_config(df: pd.DataFrame, cfg: dict) -> dict:
    analysis_cfg = cfg.get("analysis", {}) or {}
    wb_cfg = analysis_cfg.get("workbench", {}) or {}

    requested = str(wb_cfg.get("primary_dist", DEFAULT_PRIMARY_DIST) or DEFAULT_PRIMARY_DIST).strip()
    if not requested:
        requested = DEFAULT_PRIMARY_DIST

    available_raw = sorted(df.get("roi_prior_dist", pd.Series(dtype=object)).dropna().astype(str).unique().tolist())
    available_norm = {_normalize_dist(x): str(x) for x in available_raw}
    requested_norm = _normalize_dist(requested)

    if requested_norm in available_norm:
        primary_dist = available_norm[requested_norm]
        fallback = False
    elif "lognormal" in available_norm:
        primary_dist = available_norm["lognormal"]
        fallback = True
    elif available_raw:
        primary_dist = available_raw[0]
        fallback = True
    else:
        primary_dist = requested
        fallback = True

    allow_legacy = bool(wb_cfg.get("allow_legacy_distribution_debug", False))
    return {
        "primary_dist": str(primary_dist),
        "primary_dist_requested": requested,
        "primary_dist_fallback_used": bool(fallback),
        "allow_legacy_distribution_debug": allow_legacy,
        "available_dists": available_raw,
    }


def _build_run_level_table(
    merged: pd.DataFrame,
    dist_cfg: dict,
) -> tuple[pd.DataFrame, str | None, str | None, str]:
    work = merged.copy()
    primary_dist_norm = _normalize_dist(dist_cfg["primary_dist"])
    work["roi_prior_dist"] = _col_series(work, "roi_prior_dist", "").astype(str)
    work["dist_normalized"] = work["roi_prior_dist"].map(_normalize_dist)

    contribution_col, contribution_delta_col, contribution_note = _pick_contribution_cols(work)

    work["estimated_roi"] = pd.to_numeric(_col_series(work, "estimated_roi"), errors="coerce")
    baseline_src = _col_series(work, "baseline_roi_for_rank") if "baseline_roi_for_rank" in work.columns else _col_series(work, "baseline_roi")
    work["baseline_roi"] = pd.to_numeric(baseline_src, errors="coerce")
    work["pct_change"] = pd.to_numeric(_col_series(work, "pct_change"), errors="coerce")
    delta_abs_src = _col_series(work, "delta_abs") if "delta_abs" in work.columns else _col_series(work, "max_abs_delta_roi")
    work["delta_abs"] = pd.to_numeric(delta_abs_src, errors="coerce")
    work["delta_pct"] = pd.to_numeric(_col_series(work, "delta_pct"), errors="coerce")
    work["roi_prior_mu"] = pd.to_numeric(_col_series(work, "roi_prior_mu"), errors="coerce")
    work["roi_prior_sigma"] = pd.to_numeric(_col_series(work, "roi_prior_sigma"), errors="coerce")
    work["is_baseline"] = _col_series(work, "is_baseline", False).astype(str).str.lower().isin({"true", "1", "yes"})

    if contribution_col is not None:
        work["contribution_value"] = pd.to_numeric(work[contribution_col], errors="coerce")
    else:
        work["contribution_value"] = np.nan

    if contribution_delta_col is not None:
        work["contribution_delta"] = pd.to_numeric(work[contribution_delta_col], errors="coerce")
    else:
        work["contribution_delta"] = np.nan

    parsed_struct = work.get("run_id", pd.Series([""] * len(work), index=work.index)).map(_parse_structural_from_run_id)

    for col in ["adstock_alpha_m", "saturation_ec_m", "saturation_slope_m", "max_lag"]:
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")
        else:
            work[col] = np.nan
        parsed_vals = parsed_struct.map(lambda d: _safe_float(d.get(col) if isinstance(d, dict) else None))
        work[col] = work[col].where(work[col].notna(), parsed_vals)

    decay_col = "adstock_decay_spec"
    if decay_col in work.columns:
        work[decay_col] = work[decay_col].fillna("").astype(str).str.lower()
    else:
        work[decay_col] = ""
    parsed_decay = parsed_struct.map(lambda d: str(d.get(decay_col, "")).strip().lower() if isinstance(d, dict) else "")
    work[decay_col] = np.where(work[decay_col].str.len() > 0, work[decay_col], parsed_decay)
    work[decay_col] = np.where(work[decay_col].str.len() > 0, work[decay_col], "geometric")

    work["channel_total_spend"] = pd.to_numeric(_col_series(work, "channel_total_spend"), errors="coerce")
    work["effect_value"] = pd.to_numeric(_col_series(work, "incremental_value_new"), errors="coerce")
    if work["effect_value"].isna().all():
        work["effect_value"] = pd.to_numeric(_col_series(work, "incremental_outcome_new"), errors="coerce")
    if work["effect_value"].isna().all():
        work["effect_value"] = work["estimated_roi"] * work["channel_total_spend"]

    if "run_id" in work.columns:
        totals = (
            work.groupby("run_id", dropna=False)["contribution_value"]
            .sum(min_count=1)
            .rename("run_contribution_total")
        )
        work = work.merge(totals, on="run_id", how="left")
        denom = pd.to_numeric(work["run_contribution_total"], errors="coerce")
        num = pd.to_numeric(work["contribution_value"], errors="coerce")
        work["contribution_share"] = np.where(denom.abs() >= 1e-9, num / denom, np.nan)

        spend_totals = (
            work.groupby("run_id", dropna=False)["channel_total_spend"]
            .sum(min_count=1)
            .rename("run_spend_total")
        )
        work = work.merge(spend_totals, on="run_id", how="left")
        spend_denom = pd.to_numeric(work["run_spend_total"], errors="coerce")
        spend_num = pd.to_numeric(work["channel_total_spend"], errors="coerce")
        work["spend_share"] = np.where(spend_denom.abs() >= 1e-9, spend_num / spend_denom, np.nan)

        effect_totals = (
            work.groupby("run_id", dropna=False)["effect_value"]
            .sum(min_count=1)
            .rename("run_effect_total")
        )
        work = work.merge(effect_totals, on="run_id", how="left")
        effect_denom = pd.to_numeric(work["run_effect_total"], errors="coerce")
        effect_num = pd.to_numeric(work["effect_value"], errors="coerce")
        work["effect_share"] = np.where(effect_denom.abs() >= 1e-9, effect_num / effect_denom, np.nan)
    else:
        work["run_contribution_total"] = np.nan
        work["contribution_share"] = np.nan
        work["run_spend_total"] = np.nan
        work["spend_share"] = np.nan
        work["run_effect_total"] = np.nan
        work["effect_share"] = np.nan

    filtered = work[work["dist_normalized"] == primary_dist_norm].copy()
    filter_reason = ""
    if filtered.empty:
        filtered = work.copy()
        filter_reason = "primary distribution rows were empty; fell back to all distributions"
    else:
        filter_reason = f"filtered to primary distribution '{dist_cfg['primary_dist']}'"

    ordered_cols = [
        "run_id",
        "channel",
        "target_channel",
        "targets",
        "roi_prior_mu",
        "roi_prior_sigma",
        "roi_prior_dist",
        "dist_normalized",
        "is_baseline",
        "estimated_roi",
        "baseline_roi",
        "pct_change",
        "delta_abs",
        "delta_pct",
        "contribution_value",
        "contribution_delta",
        "contribution_share",
        "run_contribution_total",
        "effect_value",
        "effect_share",
        "channel_total_spend",
        "spend_share",
        "adstock_alpha_m",
        "saturation_ec_m",
        "saturation_slope_m",
        "max_lag",
        "adstock_decay_spec",
        "qc_status_code",
        "qc_summary_short",
    ]
    cols = [c for c in ordered_cols if c in filtered.columns]
    filtered = filtered[cols].copy()
    return filtered, contribution_col, contribution_delta_col, f"{filter_reason}; {contribution_note}"


def _build_channel_summary(run_level_df: pd.DataFrame) -> pd.DataFrame:
    if run_level_df.empty:
        return pd.DataFrame()

    group = run_level_df.groupby("channel", as_index=False)
    summary = group.agg(
        n_runs=("channel", "size"),
        n_baseline_rows=("is_baseline", "sum"),
        roi_median=("estimated_roi", "median"),
        roi_mean=("estimated_roi", "mean"),
        roi_min=("estimated_roi", "min"),
        roi_max=("estimated_roi", "max"),
        pct_change_abs_max=("pct_change", lambda s: pd.to_numeric(s, errors="coerce").abs().max()),
        delta_abs_max=("delta_abs", "max"),
        contribution_median=("contribution_value", "median"),
        contribution_min=("contribution_value", "min"),
        contribution_max=("contribution_value", "max"),
        contribution_share_median=("contribution_share", "median"),
        spend_share_median=("spend_share", "median"),
        effect_share_median=("effect_share", "median"),
    )
    summary["roi_range"] = summary["roi_max"] - summary["roi_min"]
    summary["contribution_range"] = summary["contribution_max"] - summary["contribution_min"]
    summary = summary.sort_values("roi_range", ascending=False).reset_index(drop=True)
    return summary


def _build_marginal_tables(run_level_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if run_level_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    mu_marginal = (
        run_level_df.groupby(["channel", "roi_prior_mu"], as_index=False)
        .agg(
            n_points=("channel", "size"),
            roi_median=("estimated_roi", "median"),
            roi_mean=("estimated_roi", "mean"),
            roi_min=("estimated_roi", "min"),
            roi_max=("estimated_roi", "max"),
            pct_change_median=("pct_change", "median"),
            contribution_median=("contribution_value", "median"),
            contribution_value_mean=("contribution_value", "mean"),
        )
    )
    mu_marginal["roi_range_over_sigma"] = mu_marginal["roi_max"] - mu_marginal["roi_min"]

    sigma_marginal = (
        run_level_df.groupby(["channel", "roi_prior_sigma"], as_index=False)
        .agg(
            n_points=("channel", "size"),
            roi_median=("estimated_roi", "median"),
            roi_mean=("estimated_roi", "mean"),
            roi_min=("estimated_roi", "min"),
            roi_max=("estimated_roi", "max"),
            pct_change_median=("pct_change", "median"),
            contribution_median=("contribution_value", "median"),
            contribution_value_mean=("contribution_value", "mean"),
        )
    )
    sigma_marginal["roi_range_over_mu"] = sigma_marginal["roi_max"] - sigma_marginal["roi_min"]
    return mu_marginal, sigma_marginal


def _build_sensitivity_split_tables(run_level_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if run_level_df.empty:
        empty = pd.DataFrame()
        return empty, empty, empty

    mu_slice = (
        run_level_df.groupby(["channel", "roi_prior_sigma"], as_index=False)
        .agg(
            n_mu_points=("roi_prior_mu", "nunique"),
            roi_min=("estimated_roi", "min"),
            roi_max=("estimated_roi", "max"),
            contribution_min=("contribution_value", "min"),
            contribution_max=("contribution_value", "max"),
            pct_change_abs_max=("pct_change", lambda s: pd.to_numeric(s, errors="coerce").abs().max()),
        )
    )
    mu_slice["mu_sensitivity_roi_range"] = mu_slice["roi_max"] - mu_slice["roi_min"]
    mu_slice["mu_sensitivity_contribution_range"] = mu_slice["contribution_max"] - mu_slice["contribution_min"]

    sigma_slice = (
        run_level_df.groupby(["channel", "roi_prior_mu"], as_index=False)
        .agg(
            n_sigma_points=("roi_prior_sigma", "nunique"),
            roi_min=("estimated_roi", "min"),
            roi_max=("estimated_roi", "max"),
            contribution_min=("contribution_value", "min"),
            contribution_max=("contribution_value", "max"),
            pct_change_abs_max=("pct_change", lambda s: pd.to_numeric(s, errors="coerce").abs().max()),
        )
    )
    sigma_slice["sigma_sensitivity_roi_range"] = sigma_slice["roi_max"] - sigma_slice["roi_min"]
    sigma_slice["sigma_sensitivity_contribution_range"] = sigma_slice["contribution_max"] - sigma_slice["contribution_min"]

    mu_summary = (
        mu_slice.groupby("channel", as_index=False)
        .agg(
            mu_slice_count=("roi_prior_sigma", "size"),
            mu_sensitivity_roi_median=("mu_sensitivity_roi_range", "median"),
            mu_sensitivity_roi_max=("mu_sensitivity_roi_range", "max"),
            mu_sensitivity_contribution_median=("mu_sensitivity_contribution_range", "median"),
            mu_sensitivity_contribution_max=("mu_sensitivity_contribution_range", "max"),
        )
    )
    sigma_summary = (
        sigma_slice.groupby("channel", as_index=False)
        .agg(
            sigma_slice_count=("roi_prior_mu", "size"),
            sigma_sensitivity_roi_median=("sigma_sensitivity_roi_range", "median"),
            sigma_sensitivity_roi_max=("sigma_sensitivity_roi_range", "max"),
            sigma_sensitivity_contribution_median=("sigma_sensitivity_contribution_range", "median"),
            sigma_sensitivity_contribution_max=("sigma_sensitivity_contribution_range", "max"),
        )
    )

    split = mu_summary.merge(sigma_summary, on="channel", how="outer")
    split["mu_vs_sigma_roi_ratio"] = np.where(
        pd.to_numeric(split["sigma_sensitivity_roi_median"], errors="coerce").abs() >= 1e-12,
        pd.to_numeric(split["mu_sensitivity_roi_median"], errors="coerce")
        / pd.to_numeric(split["sigma_sensitivity_roi_median"], errors="coerce"),
        np.nan,
    )
    split["dominant_driver"] = np.select(
        [
            pd.to_numeric(split["mu_vs_sigma_roi_ratio"], errors="coerce") >= 1.15,
            pd.to_numeric(split["mu_vs_sigma_roi_ratio"], errors="coerce") <= (1.0 / 1.15),
        ],
        ["mu", "sigma"],
        default="balanced",
    )

    mu_rank = split[
        [
            "channel",
            "mu_sensitivity_roi_median",
            "mu_sensitivity_roi_max",
            "mu_sensitivity_contribution_median",
            "mu_sensitivity_contribution_max",
        ]
    ].sort_values("mu_sensitivity_roi_median", ascending=False, na_position="last")
    sigma_rank = split[
        [
            "channel",
            "sigma_sensitivity_roi_median",
            "sigma_sensitivity_roi_max",
            "sigma_sensitivity_contribution_median",
            "sigma_sensitivity_contribution_max",
        ]
    ].sort_values("sigma_sensitivity_roi_median", ascending=False, na_position="last")
    return split, mu_rank.reset_index(drop=True), sigma_rank.reset_index(drop=True)


def build_workbench_artifacts(
    merged: pd.DataFrame,
    cfg: dict,
    tables_dir: Path,
) -> dict:
    dist_cfg = resolve_workbench_dist_config(merged, cfg)
    run_level_df, contribution_col, contribution_delta_col, notes = _build_run_level_table(merged, dist_cfg)
    channel_summary_df = _build_channel_summary(run_level_df)
    mu_marginal_df, sigma_marginal_df = _build_marginal_tables(run_level_df)
    sensitivity_split_df, mu_rank_df, sigma_rank_df = _build_sensitivity_split_tables(run_level_df)

    tables_dir.mkdir(parents=True, exist_ok=True)
    run_level_df.to_csv(tables_dir / "workbench_run_level.csv", index=False)
    channel_summary_df.to_csv(tables_dir / "workbench_channel_summary.csv", index=False)
    mu_marginal_df.to_csv(tables_dir / "workbench_mu_marginal_summary.csv", index=False)
    sigma_marginal_df.to_csv(tables_dir / "workbench_sigma_marginal_summary.csv", index=False)
    sensitivity_split_df.to_csv(tables_dir / "workbench_mu_sigma_split_summary.csv", index=False)
    mu_rank_df.to_csv(tables_dir / "workbench_mu_sensitivity_rank.csv", index=False)
    sigma_rank_df.to_csv(tables_dir / "workbench_sigma_sensitivity_rank.csv", index=False)

    default_channel = None
    wb_cfg = (cfg.get("analysis", {}) or {}).get("workbench", {}) or {}
    wanted_default = str(wb_cfg.get("default_channel", "") or "").strip().lower()
    available_channels = run_level_df.get("channel", pd.Series(dtype=object)).dropna().astype(str).tolist()
    available_channels_sorted = sorted(set(available_channels))
    if wanted_default:
        for c in available_channels_sorted:
            if c.lower() == wanted_default:
                default_channel = c
                break
    if default_channel is None and available_channels_sorted:
        default_channel = available_channels_sorted[0]

    return {
        "available": True,
        "dist_config": dist_cfg,
        "notes": notes,
        "contribution_col": contribution_col,
        "contribution_delta_col": contribution_delta_col,
        "default_channel": default_channel,
        "available_channels": available_channels_sorted,
        "mu_values": _sorted_numeric(run_level_df.get("roi_prior_mu", pd.Series(dtype=float))),
        "sigma_values": _sorted_numeric(run_level_df.get("roi_prior_sigma", pd.Series(dtype=float))),
        "run_level_df": run_level_df,
        "channel_summary_df": channel_summary_df,
        "mu_marginal_df": mu_marginal_df,
        "sigma_marginal_df": sigma_marginal_df,
        "sensitivity_split_df": sensitivity_split_df,
        "mu_rank_df": mu_rank_df,
        "sigma_rank_df": sigma_rank_df,
    }
