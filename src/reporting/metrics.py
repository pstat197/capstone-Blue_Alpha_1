from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

STRUCTURAL_COLS = [
    "adstock_alpha_m",
    "saturation_ec_m",
    "saturation_slope_m",
    "max_lag",
    "adstock_decay_spec",
]

DEFAULT_STRUCTURAL = {
    "adstock_alpha_m": np.nan,
    "saturation_ec_m": np.nan,
    "saturation_slope_m": 1.0,
    "max_lag": 8,
    "adstock_decay_spec": "geometric",
}

DEFAULT_QC_GATE_MU = [0.020759, 0.051898]
DEFAULT_QC_GATE_SIGMA = [0.006689, 0.033445]
DEFAULT_QC_GATE_DISTS = ["Normal"]

def _fmt_money_short(x: float) -> str:
    sign = "-" if x < 0 else ""
    ax = abs(float(x))
    if ax >= 1_000_000_000:
        return f"{sign}${ax/1_000_000_000:.2f}B"
    if ax >= 1_000_000:
        return f"{sign}${ax/1_000_000:.2f}M"
    if ax >= 1_000:
        return f"{sign}${ax/1_000:.1f}K"
    return f"{sign}${ax:,.2f}"


def _pick_baseline(group: pd.DataFrame, rule: str) -> tuple[float, float]:
    if rule == "median":
        return float(group["roi_prior_mu"].median()), float(group["roi_prior_sigma"].median())
    raise ValueError(f"Unknown baseline rule: {rule}")


def _parse_linked_targets(raw_target_values: list[str]) -> list[str]:
    linked: list[str] = []
    seen: set[str] = set()
    for raw in raw_target_values:
        for tok in str(raw).split(","):
            t = tok.strip()
            if t and t not in seen:
                seen.add(t)
                linked.append(t)
    return linked


def _build_scope_info(df: pd.DataFrame) -> dict:
    raw_target_values = sorted(df["target_channel"].dropna().astype(str).unique().tolist())
    linked_targets = _parse_linked_targets(raw_target_values)
    looks_linked = len(raw_target_values) == 1 and len(linked_targets) > 1

    if looks_linked:
        mode = "linked_targets"
        note = (
            "The listed target channels were perturbed together in each run (linked prior changes). "
            "The report then measures ROI response for all modeled channels under those shared target priors."
        )
    else:
        mode = "single_or_mixed"
        note = (
            "Prior changes were applied per available target setting in the input; "
            "ROI responses are still summarized across all modeled channels."
        )

    return {
        "mode": mode,
        "target_sets": raw_target_values,
        "linked_targets": linked_targets,
        "note": note,
    }


def _status_bucket(value: object) -> str:
    txt = str(value).strip()
    if not txt or txt.lower() in {"nan", "none", "na", "n/a"}:
        return "UNKNOWN"
    head = txt.split(":", 1)[0].strip().upper()
    if head in {"PASS", "REVIEW", "FAIL"}:
        return head
    return "UNKNOWN"


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    txt = str(value).strip().lower()
    return txt in {"1", "true", "t", "yes", "y"}



def _safe_float(value: object) -> float | None:
    try:
        out = float(value)
        if np.isnan(out):
            return None
        return out
    except Exception:
        return None


def _struct_profile_id(alpha: object, ec: object, slope: object, max_lag: object, decay: object) -> str:
    def _fmt(x: object, key: str) -> str:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return f"{key}=NA"
        if isinstance(x, (int, float, np.number)):
            return f"{key}={float(x):.4f}"
        return f"{key}={str(x)}"

    return "|".join(
        [
            _fmt(alpha, "alpha"),
            _fmt(ec, "ec"),
            _fmt(slope, "slope"),
            _fmt(max_lag, "lag"),
            _fmt(decay, "decay"),
        ]
    )


def _compute_adstock_weights(alpha: float | None, max_lag: int, decay_spec: str) -> np.ndarray:
    lags = np.arange(max(0, int(max_lag)) + 1, dtype=float)
    if len(lags) == 0:
        return np.array([1.0], dtype=float)

    if alpha is None:
        w = np.zeros_like(lags)
        w[0] = 1.0
        return w

    a = max(0.0, min(0.999999, float(alpha)))
    decay = str(decay_spec or "geometric").strip().lower()
    if decay == "binomial":
        # Matches Meridian mapping in adstock_hill.py:
        # mapped_alpha = 1/alpha - 1, weights = (1 - lag/window_size)^mapped_alpha
        window_size = float(len(lags))
        if a <= 0.0:
            raw = np.zeros_like(lags)
            raw[0] = 1.0
        else:
            mapped = 1.0 / a - 1.0
            raw = (1.0 - lags / window_size) ** mapped
    else:
        raw = a ** lags

    s = float(np.sum(raw))
    if not np.isfinite(s) or s <= 0:
        out = np.zeros_like(lags)
        out[0] = 1.0
        return out
    return raw / s


def _half_life_from_weights(weights: np.ndarray) -> float | None:
    if weights.size == 0:
        return None
    w0 = float(weights[0])
    if not np.isfinite(w0) or w0 <= 0:
        return None
    threshold = 0.5 * w0
    below = np.where(weights <= threshold)[0]
    if len(below) == 0:
        return None
    idx = int(below[0])
    if idx == 0:
        return 0.0
    w_prev = float(weights[idx - 1])
    w_cur = float(weights[idx])
    if np.isclose(w_prev, w_cur):
        return float(idx)
    frac = (threshold - w_prev) / (w_cur - w_prev)
    return float((idx - 1) + frac)

def _compute_diagnostics(run_level_df: pd.DataFrame, tables_dir: Path) -> dict:
    if run_level_df.empty:
        return {"available": False, "reason": "No rows available."}

    if "run_id" in run_level_df.columns:
        run_rows = run_level_df.drop_duplicates(subset=["run_id"]).copy()
    else:
        # Fallback only for legacy inputs where run_id might be absent.
        key_cols = [c for c in ["target_channel", "roi_prior_mu", "roi_prior_sigma", "roi_prior_dist"] if c in run_level_df.columns]
        run_rows = run_level_df.drop_duplicates(subset=key_cols).copy() if key_cols else run_level_df.copy()

    diag_cols = [c for c in run_rows.columns if c.startswith("qc_")]
    if not diag_cols and "is_baseline" not in run_rows.columns:
        return {"available": False, "reason": "No diagnostic columns found in report input."}

    if "qc_status_code" in run_rows.columns:
        run_rows["diag_status"] = run_rows["qc_status_code"].map(_status_bucket)
    elif "qc_summary_short" in run_rows.columns:
        run_rows["diag_status"] = run_rows["qc_summary_short"].map(_status_bucket)
    else:
        run_rows["diag_status"] = "UNKNOWN"

    if "qc_needs_review" in run_rows.columns:
        review_mask = run_rows["qc_needs_review"].map(_to_bool)
        run_rows.loc[(run_rows["diag_status"] == "UNKNOWN") & review_mask, "diag_status"] = "REVIEW"

    n_runs = int(run_rows.shape[0])
    status_order = ["PASS", "REVIEW", "FAIL", "UNKNOWN"]
    status_counts = run_rows["diag_status"].value_counts()
    status_df = pd.DataFrame(
        {
            "status": status_order,
            "count": [int(status_counts.get(s, 0)) for s in status_order],
        }
    )
    status_df["pct_runs"] = np.where(n_runs > 0, 100.0 * status_df["count"] / float(n_runs), 0.0)
    status_df = status_df[status_df["count"] > 0].reset_index(drop=True)

    primary_df = pd.DataFrame(columns=["check", "count", "pct_runs"])
    if "qc_primary_review_check" in run_rows.columns:
        checks = (
            run_rows["qc_primary_review_check"]
            .fillna("")
            .astype(str)
            .str.strip()
        )
        checks = checks[~checks.str.lower().isin({"", "none", "nan", "na", "n/a"})]
        if not checks.empty:
            primary_counts = checks.value_counts()
            primary_df = (
                pd.DataFrame({"check": primary_counts.index, "count": primary_counts.values})
                .head(10)
                .reset_index(drop=True)
            )
            primary_df["pct_runs"] = np.where(n_runs > 0, 100.0 * primary_df["count"] / float(n_runs), 0.0)

    flagged_df = pd.DataFrame(columns=["channel", "count", "pct_runs"])
    if "qc_flagged_channels" in run_rows.columns:
        tokens: list[str] = []
        for raw in run_rows["qc_flagged_channels"].fillna("").astype(str).tolist():
            for tok in raw.split(","):
                t = tok.strip().lower()
                if t and t not in {"none", "nan", "na", "n/a"}:
                    tokens.append(t)
        if tokens:
            flagged_counts = pd.Series(tokens).value_counts()
            flagged_df = (
                pd.DataFrame({"channel": flagged_counts.index, "count": flagged_counts.values})
                .head(10)
                .reset_index(drop=True)
            )
            flagged_df["pct_runs"] = np.where(n_runs > 0, 100.0 * flagged_df["count"] / float(n_runs), 0.0)

    check_cols = [
        c
        for c in [
            "qc_convergence_status",
            "qc_baseline_status",
            "qc_bayesianppp_status",
            "qc_gof_status",
            "qc_prior_posterior_shift_status",
            "qc_roi_consistency_status",
        ]
        if c in run_rows.columns
    ]
    check_rows: list[dict] = []
    for col in check_cols:
        buckets = run_rows[col].map(_status_bucket)
        counts = buckets.value_counts()
        total = int(counts.sum())
        check_rows.append(
            {
                "check": col.replace("qc_", "").replace("_status", ""),
                "pass_count": int(counts.get("PASS", 0)),
                "review_count": int(counts.get("REVIEW", 0)),
                "fail_count": int(counts.get("FAIL", 0)),
                "unknown_count": int(counts.get("UNKNOWN", 0)),
                "coverage_pct": (100.0 * total / float(n_runs)) if n_runs > 0 else 0.0,
            }
        )
    check_df = pd.DataFrame(check_rows)

    overview = {
        "n_runs": n_runs,
        "pass_runs": int((run_rows["diag_status"] == "PASS").sum()),
        "review_runs": int((run_rows["diag_status"] == "REVIEW").sum()),
        "fail_runs": int((run_rows["diag_status"] == "FAIL").sum()),
        "unknown_runs": int((run_rows["diag_status"] == "UNKNOWN").sum()),
    }
    if n_runs > 0:
        overview["pass_rate_pct"] = 100.0 * overview["pass_runs"] / float(n_runs)
        overview["review_rate_pct"] = 100.0 * overview["review_runs"] / float(n_runs)
        overview["fail_rate_pct"] = 100.0 * overview["fail_runs"] / float(n_runs)
    else:
        overview["pass_rate_pct"] = 0.0
        overview["review_rate_pct"] = 0.0
        overview["fail_rate_pct"] = 0.0

    status_df.to_csv(tables_dir / "diagnostics_status_breakdown.csv", index=False)
    primary_df.to_csv(tables_dir / "diagnostics_primary_checks.csv", index=False)
    flagged_df.to_csv(tables_dir / "diagnostics_flagged_channels.csv", index=False)
    check_df.to_csv(tables_dir / "diagnostics_check_matrix.csv", index=False)

    return {
        "available": True,
        "overview": overview,
        "status_rows": status_df.to_dict(orient="records"),
        "primary_rows": primary_df.to_dict(orient="records"),
        "flagged_rows": flagged_df.to_dict(orient="records"),
        "check_rows": check_df.to_dict(orient="records"),
    }



def _compute_qc_gate(run_level_df: pd.DataFrame, merged_df: pd.DataFrame, cfg: dict, tables_dir: Path) -> dict:
    qc_cfg = cfg.get("analysis", {}).get("qc_gate", {}) or {}
    enabled = bool(qc_cfg.get("enabled", False))
    if not enabled:
        return {"available": False, "enabled": False, "reason": "QC gate disabled in report config."}

    if run_level_df.empty:
        return {"available": False, "enabled": True, "reason": "No rows available."}

    if "run_id" in run_level_df.columns:
        run_rows = run_level_df.drop_duplicates(subset=["run_id"]).copy()
    else:
        key_cols = [
            c
            for c in ["target_channel", "roi_prior_mu", "roi_prior_sigma", "roi_prior_dist"]
            if c in run_level_df.columns
        ]
        run_rows = run_level_df.drop_duplicates(subset=key_cols).copy() if key_cols else run_level_df.copy()

    required = {"roi_prior_mu", "roi_prior_sigma", "roi_prior_dist"}
    if not required.issubset(run_rows.columns):
        missing = sorted(required - set(run_rows.columns))
        return {
            "available": False,
            "enabled": True,
            "reason": f"Missing required columns for QC gate: {missing}",
        }

    def _to_float_list(raw_values, defaults: list[float]) -> list[float]:
        vals = raw_values if isinstance(raw_values, list) and raw_values else defaults
        out: list[float] = []
        for v in vals:
            try:
                out.append(round(float(v), 6))
            except Exception:
                continue
        return sorted(set(out))

    def _to_str_list(raw_values, defaults: list[str]) -> list[str]:
        vals = raw_values if isinstance(raw_values, list) and raw_values else defaults
        out: list[str] = []
        for v in vals:
            s = str(v).strip()
            if s:
                out.append(s)
        return sorted(set(out))

    mu_values = _to_float_list(qc_cfg.get("mu_values"), DEFAULT_QC_GATE_MU)
    sigma_values = _to_float_list(qc_cfg.get("sigma_values"), DEFAULT_QC_GATE_SIGMA)
    dists = _to_str_list(qc_cfg.get("dists"), DEFAULT_QC_GATE_DISTS)

    if not mu_values or not sigma_values or not dists:
        return {
            "available": False,
            "enabled": True,
            "reason": "QC gate config has empty mu/sigma/dist lists.",
        }

    if "qc_status_code" in run_rows.columns:
        run_rows["qc_status_bucket"] = run_rows["qc_status_code"].map(_status_bucket)
    elif "qc_summary_short" in run_rows.columns:
        run_rows["qc_status_bucket"] = run_rows["qc_summary_short"].map(_status_bucket)
    else:
        run_rows["qc_status_bucket"] = "UNKNOWN"

    run_rows["_mu"] = pd.to_numeric(run_rows["roi_prior_mu"], errors="coerce").round(6)
    run_rows["_sigma"] = pd.to_numeric(run_rows["roi_prior_sigma"], errors="coerce").round(6)
    run_rows["_dist"] = run_rows["roi_prior_dist"].astype(str).str.strip()

    subset = run_rows[
        run_rows["_mu"].isin(mu_values)
        & run_rows["_sigma"].isin(sigma_values)
        & run_rows["_dist"].isin(dists)
    ].copy()

    if subset.empty:
        return {
            "available": False,
            "enabled": True,
            "reason": "No runs matched configured QC gate window.",
            "mu_values": mu_values,
            "sigma_values": sigma_values,
            "dists": dists,
        }

    subset_ids = set(subset["run_id"].astype(str).tolist()) if "run_id" in subset.columns else set()
    outside = run_rows.copy()
    if subset_ids and "run_id" in outside.columns:
        outside = outside[~outside["run_id"].astype(str).isin(subset_ids)].copy()

    n_total = int(run_rows.shape[0])
    n_qc = int(subset.shape[0])
    n_pass = int((subset["qc_status_bucket"] == "PASS").sum())
    n_review = int((subset["qc_status_bucket"] == "REVIEW").sum())
    n_fail = int((subset["qc_status_bucket"] == "FAIL").sum())
    pass_rate_pct = 100.0 * n_pass / float(n_qc) if n_qc > 0 else 0.0
    gate_result = "PASS" if (n_review == 0 and n_fail == 0 and n_qc > 0) else "REVIEW"

    status_order = ["PASS", "REVIEW", "FAIL", "UNKNOWN"]
    status_counts = subset["qc_status_bucket"].value_counts()
    status_df = pd.DataFrame(
        {
            "status": status_order,
            "count": [int(status_counts.get(s, 0)) for s in status_order],
        }
    )
    status_df["pct_runs"] = np.where(n_qc > 0, 100.0 * status_df["count"] / float(n_qc), 0.0)
    status_df = status_df[status_df["count"] > 0].reset_index(drop=True)

    outside_counts_raw = outside["qc_status_bucket"].value_counts().to_dict()
    outside_counts = {
        "PASS": int(outside_counts_raw.get("PASS", 0)),
        "REVIEW": int(outside_counts_raw.get("REVIEW", 0)),
        "FAIL": int(outside_counts_raw.get("FAIL", 0)),
        "UNKNOWN": int(outside_counts_raw.get("UNKNOWN", 0)),
    }

    mean_r2 = pd.to_numeric(subset.get("qc_r2", pd.Series(dtype=float)), errors="coerce").mean()
    mean_mape = pd.to_numeric(subset.get("qc_mape", pd.Series(dtype=float)), errors="coerce").mean()
    mean_wmape = pd.to_numeric(subset.get("qc_wmape", pd.Series(dtype=float)), errors="coerce").mean()
    max_baseline_neg_prob = pd.to_numeric(
        subset.get("qc_baseline_neg_prob", pd.Series(dtype=float)), errors="coerce"
    ).max()

    run_cols = [
        c
        for c in [
            "run_id",
            "roi_prior_mu",
            "roi_prior_sigma",
            "roi_prior_dist",
            "qc_status_code",
            "qc_primary_review_check",
            "qc_flagged_channels",
            "qc_baseline_neg_prob",
            "qc_r2",
            "qc_mape",
            "qc_wmape",
        ]
        if c in subset.columns
    ]
    run_subset_df = subset[run_cols].copy().sort_values(
        [c for c in ["roi_prior_mu", "roi_prior_sigma", "roi_prior_dist"] if c in run_cols],
        ascending=True,
    )

    run_subset_df.to_csv(tables_dir / "qc_gate_run_subset.csv", index=False)
    status_df.to_csv(tables_dir / "qc_gate_status_breakdown.csv", index=False)

    rank_metric = None
    rank_df = pd.DataFrame()
    if not merged_df.empty and {"run_id", "channel"}.issubset(merged_df.columns):
        qmerged = merged_df.copy()
        if subset_ids:
            qmerged = qmerged[qmerged["run_id"].astype(str).isin(subset_ids)].copy()

        metric_candidates = ["delta_value_abs", "delta_outcome_abs", "delta_abs", "abs_pct_change"]
        for c in metric_candidates:
            if c in qmerged.columns:
                rank_metric = c
                break

        if rank_metric is not None and not qmerged.empty:
            qmerged[rank_metric] = pd.to_numeric(qmerged[rank_metric], errors="coerce")
            rank_df = (
                qmerged.groupby("channel", as_index=False)[rank_metric]
                .agg(["max", "median", "mean", "count"])
                .reset_index()
                .rename(
                    columns={
                        "max": "max_change",
                        "median": "median_change",
                        "mean": "mean_change",
                        "count": "n",
                    }
                )
                .sort_values("max_change", ascending=False, na_position="last")
                .reset_index(drop=True)
            )
            rank_df.to_csv(tables_dir / "qc_gate_channel_sensitivity.csv", index=False)

    quick_lines: list[str] = []
    if not rank_df.empty and rank_metric is not None:
        for row in rank_df.head(5).itertuples(index=False):
            if rank_metric == "delta_value_abs":
                quick_lines.append(f"{row.channel}: max={_fmt_money_short(row.max_change)} (n={int(row.n)})")
            elif rank_metric == "abs_pct_change":
                quick_lines.append(f"{row.channel}: max={float(row.max_change):.2f}% (n={int(row.n)})")
            else:
                quick_lines.append(f"{row.channel}: max={float(row.max_change):.4f} (n={int(row.n)})")

    return {
        "available": True,
        "enabled": True,
        "result": gate_result,
        "mu_values": mu_values,
        "sigma_values": sigma_values,
        "dists": dists,
        "overview": {
            "n_total_runs": n_total,
            "n_qc_runs": n_qc,
            "pass_runs": n_pass,
            "review_runs": n_review,
            "fail_runs": n_fail,
            "pass_rate_pct": pass_rate_pct,
            "outside_counts": outside_counts,
            "mean_r2": None if pd.isna(mean_r2) else float(mean_r2),
            "mean_mape": None if pd.isna(mean_mape) else float(mean_mape),
            "mean_wmape": None if pd.isna(mean_wmape) else float(mean_wmape),
            "max_baseline_neg_prob": None if pd.isna(max_baseline_neg_prob) else float(max_baseline_neg_prob),
        },
        "status_rows": status_df.to_dict(orient="records"),
        "run_rows": run_subset_df.to_dict(orient="records"),
        "rank_metric": rank_metric,
        "rank_rows": rank_df.head(8).to_dict(orient="records") if not rank_df.empty else [],
        "quick_lines": quick_lines,
    }
def _compute_dollar_sensitivity(merged: pd.DataFrame, cfg: dict, tables_dir: Path) -> dict:
    source = None
    if "delta_value" in merged.columns:
        delta_series = pd.to_numeric(merged["delta_value"], errors="coerce")
        source = "delta_value"
    elif {"incremental_value_new", "incremental_value_baseline"}.issubset(merged.columns):
        delta_series = (
            pd.to_numeric(merged["incremental_value_new"], errors="coerce")
            - pd.to_numeric(merged["incremental_value_baseline"], errors="coerce")
        )
        source = "incremental_value_new - incremental_value_baseline"
    elif {"delta_outcome", "dollars_per_subscription"}.issubset(merged.columns):
        delta_series = (
            pd.to_numeric(merged["delta_outcome"], errors="coerce")
            * pd.to_numeric(merged["dollars_per_subscription"], errors="coerce")
        )
        source = "delta_outcome * dollars_per_subscription"
    else:
        return {"available": False, "reason": "No dollar-change columns found in report input."}

    work = merged.copy()
    work["delta_value_used"] = delta_series

    range_mode = str(cfg.get("figures", {}).get("tornado_range_mode", "p05p95")).strip().lower()
    rows: list[dict] = []
    for channel, g in work.groupby("channel", as_index=False):
        vals = pd.to_numeric(g["delta_value_used"], errors="coerce").dropna().to_numpy(dtype=float)
        if len(vals) == 0:
            continue

        if range_mode == "minmax":
            left = float(np.min(vals))
            right = float(np.max(vals))
        elif range_mode == "p05p95":
            left = float(np.quantile(vals, 0.05))
            right = float(np.quantile(vals, 0.95))
        else:
            raise ValueError("figures.tornado_range_mode must be 'minmax' or 'p05p95'")

        rows.append(
            {
                "channel": channel,
                "left_dollar": left,
                "right_dollar": right,
                "max_abs_dollar_change": max(abs(left), abs(right)),
                "median_dollar_change": float(np.median(vals)),
                "mean_dollar_change": float(np.mean(vals)),
                "std_dollar_change": float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0,
                "n": int(len(vals)),
            }
        )

    if not rows:
        return {"available": False, "reason": "Dollar columns were present, but all values were missing."}

    rank = pd.DataFrame(rows).sort_values("max_abs_dollar_change", ascending=False).reset_index(drop=True)
    top_n = int(cfg["ranking"]["top_n"])
    rank_top = rank.head(top_n).copy()

    quick_n = min(3, len(rank))
    quick_rows = rank.head(quick_n).copy()
    quick_lines = []
    for r in quick_rows.itertuples(index=False):
        quick_lines.append(
            f"{r.channel}: "
            f"downside={_fmt_money_short(r.left_dollar)}, upside={_fmt_money_short(r.right_dollar)}, "
            f"max |$ change|={_fmt_money_short(r.max_abs_dollar_change)}"
        )

    dps_note = "unknown"
    if "dollars_per_subscription" in work.columns:
        dps_vals = pd.to_numeric(work["dollars_per_subscription"], errors="coerce").dropna().unique()
        if len(dps_vals) == 1:
            dps_note = f"{float(dps_vals[0]):.2f}"
        elif len(dps_vals) > 1:
            dps_note = "row-level varying"

    rank.to_csv(tables_dir / "dollar_sensitivity_rank.csv", index=False)

    return {
        "available": True,
        "source": source,
        "range_mode": range_mode,
        "dollars_per_subscription_note": dps_note,
        "rank_df": rank,
        "rank_top_df": rank_top,
        "quick_lines": quick_lines,
    }


def _compute_scenario_snapshot(merged: pd.DataFrame, cfg: dict, tables_dir: Path) -> dict:
    if merged.empty:
        return {"available": False, "reason": "No rows available."}

    selection_mode = str(
        cfg.get("analysis", {}).get("scenario_selection", "largest_total_abs_pct_non_fail")
    ).strip().lower()
    valid_modes = {"largest_total_abs_pct_non_fail", "largest_total_abs_pct", "first_non_baseline"}
    if selection_mode not in valid_modes:
        selection_mode = "largest_total_abs_pct_non_fail"

    key_cols = ["run_id"] if "run_id" in merged.columns else [
        c for c in ["target_channel", "roi_prior_mu", "roi_prior_sigma", "roi_prior_dist"] if c in merged.columns
    ]
    if not key_cols:
        return {"available": False, "reason": "Could not infer run grouping keys."}

    work = merged.copy()
    if "is_baseline" in work.columns:
        work["_is_baseline"] = work["is_baseline"].map(_to_bool)
    else:
        work["_is_baseline"] = False

    if "qc_status_code" in work.columns:
        work["_is_fail"] = work["qc_status_code"].map(_status_bucket).eq("FAIL")
    elif "qc_summary_short" in work.columns:
        work["_is_fail"] = work["qc_summary_short"].map(_status_bucket).eq("FAIL")
    else:
        work["_is_fail"] = False

    agg = (
        work.groupby(key_cols, dropna=False, as_index=False)
        .agg(
            n_rows=("channel", "size"),
            n_channels=("channel", "nunique"),
            total_abs_pct=("abs_pct_change", "sum"),
            max_abs_pct=("abs_pct_change", "max"),
            median_abs_pct=("abs_pct_change", "median"),
            any_baseline=("_is_baseline", "max"),
            any_fail=("_is_fail", "max"),
        )
    )
    if agg.empty:
        return {"available": False, "reason": "No scenario aggregates could be computed."}

    candidates = agg.loc[~agg["any_baseline"]].copy()
    if candidates.empty:
        candidates = agg.copy()

    reason = ""
    if selection_mode == "largest_total_abs_pct_non_fail":
        non_fail = candidates.loc[~candidates["any_fail"]].copy()
        if not non_fail.empty:
            chosen_pool = non_fail
            reason = "Selected non-fail scenario with largest total absolute ROI % change across channels."
        else:
            chosen_pool = candidates
            reason = "No non-fail scenario found; selected largest total absolute ROI % change across channels."
        chosen = chosen_pool.sort_values(["total_abs_pct", "max_abs_pct"], ascending=False).iloc[0]
    elif selection_mode == "largest_total_abs_pct":
        chosen = candidates.sort_values(["total_abs_pct", "max_abs_pct"], ascending=False).iloc[0]
        reason = "Selected scenario with largest total absolute ROI % change across channels."
    else:
        chosen = candidates.iloc[0]
        reason = "Selected first non-baseline scenario by input order."

    sort_cols = ["total_abs_pct", "max_abs_pct"]
    scenarios_pool = agg.sort_values(sort_cols, ascending=False).reset_index(drop=True)

    def _rows_for_group_key(group_key_row: pd.Series) -> pd.DataFrame:
        m = np.ones(len(work), dtype=bool)
        for col in key_cols:
            v = group_key_row[col]
            if pd.isna(v):
                m &= work[col].isna().to_numpy()
            else:
                m &= work[col].eq(v).to_numpy()
        return work.loc[m].copy()

    def _attach_delta_value(df_: pd.DataFrame) -> pd.DataFrame:
        out = df_.copy()
        if "delta_value" in out.columns:
            out["delta_value_used"] = pd.to_numeric(out["delta_value"], errors="coerce")
        elif {"incremental_value_new", "incremental_value_baseline"}.issubset(out.columns):
            out["delta_value_used"] = (
                pd.to_numeric(out["incremental_value_new"], errors="coerce")
                - pd.to_numeric(out["incremental_value_baseline"], errors="coerce")
            )
        elif {"delta_outcome", "dollars_per_subscription"}.issubset(out.columns):
            out["delta_value_used"] = (
                pd.to_numeric(out["delta_outcome"], errors="coerce")
                * pd.to_numeric(out["dollars_per_subscription"], errors="coerce")
            )
        else:
            out["delta_value_used"] = np.nan
        return out

    scenario_items: list[dict] = []
    for row in scenarios_pool.itertuples(index=False):
        key_row = pd.Series(row._asdict())
        rows_df = _rows_for_group_key(key_row)
        if rows_df.empty:
            continue
        rows_df = _attach_delta_value(rows_df)
        rows_df = rows_df.sort_values("abs_pct_change", ascending=False).reset_index(drop=True)

        meta = {}
        for col in [
            "run_id",
            "target_channel",
            "roi_prior_mu",
            "roi_prior_sigma",
            "roi_prior_dist",
            "qc_status_code",
            "qc_summary_short",
        ]:
            if col in rows_df.columns:
                meta[col] = rows_df.iloc[0][col]

        run_id = str(meta.get("run_id", f"scenario_{len(scenario_items)+1}"))
        label = (
            f"mu={meta.get('roi_prior_mu', 'NA')}, "
            f"sigma={meta.get('roi_prior_sigma', 'NA')}, "
            f"dist={meta.get('roi_prior_dist', 'NA')}"
        )

        scenario_items.append(
            {
                "run_id": run_id,
                "label": label,
                "meta": meta,
                "n_channels": int(rows_df["channel"].nunique()),
                "n_rows": int(rows_df.shape[0]),
                "total_abs_pct": float(getattr(row, "total_abs_pct", np.nan)),
                "max_abs_pct": float(getattr(row, "max_abs_pct", np.nan)),
                "any_fail": bool(getattr(row, "any_fail", False)),
                "rows_df": rows_df,
            }
        )

    if not scenario_items:
        return {"available": False, "reason": "No scenario rows could be materialized."}

    selected_run_id = str(chosen.get("run_id")) if "run_id" in chosen.index else scenario_items[0]["run_id"]
    selected_item = None
    for item in scenario_items:
        if item["run_id"] == selected_run_id:
            selected_item = item
            break
    if selected_item is None:
        selected_item = scenario_items[0]
        selected_run_id = selected_item["run_id"]

    keep_cols = [
        c
        for c in [
            "run_id",
            "channel",
            "target_channel",
            "roi_prior_mu",
            "roi_prior_sigma",
            "roi_prior_dist",
            "estimated_roi",
            "baseline_roi",
            "pct_change",
            "abs_pct_change",
            "delta_value_used",
            "qc_status_code",
            "qc_summary_short",
        ]
        if c in selected_item["rows_df"].columns
    ]
    selected_item["rows_df"][keep_cols].to_csv(tables_dir / "scenario_snapshot_rows.csv", index=False)

    return {
        "available": True,
        "selection_mode": selection_mode,
        "selection_reason": reason,
        "selected_run_id": selected_run_id,
        "selected_meta": selected_item["meta"],
        "n_channels": selected_item["n_channels"],
        "n_rows": selected_item["n_rows"],
        "rows_df": selected_item["rows_df"],
        "scenario_count": len(scenario_items),
        "scenarios": scenario_items,
    }




def _compute_spend_effect_onepager(
    merged: pd.DataFrame,
    scenario_snapshot: dict,
    tables_dir: Path,
) -> dict:
    if merged.empty or "channel" not in merged.columns:
        return {"available": False, "reason": "Missing channel-level rows."}

    selected_run_id = str(scenario_snapshot.get("selected_run_id", "") or "")
    run_df = pd.DataFrame()
    if selected_run_id and "run_id" in merged.columns:
        run_df = merged[merged["run_id"].astype(str) == selected_run_id].copy()

    if run_df.empty:
        run_df = merged.copy()
        if "is_baseline" in run_df.columns:
            run_df = run_df.loc[~run_df["is_baseline"].map(_to_bool)].copy()
        if "qc_status_code" in run_df.columns:
            non_fail = run_df.loc[run_df["qc_status_code"].map(_status_bucket) != "FAIL"].copy()
            if not non_fail.empty:
                run_df = non_fail
        if "run_id" in run_df.columns:
            order = (
                run_df.groupby("run_id", as_index=False)["abs_pct_change"]
                .sum(min_count=1)
                .sort_values("abs_pct_change", ascending=False)
            )
            if not order.empty:
                selected_run_id = str(order.iloc[0]["run_id"])
                run_df = run_df[run_df["run_id"].astype(str) == selected_run_id].copy()

    if run_df.empty:
        return {"available": False, "reason": "Could not identify a selected scenario run for one-pager table."}
    if "run_id" in run_df.columns and not selected_run_id:
        selected_run_id = str(run_df["run_id"].astype(str).iloc[0])

    rows = run_df[["channel"]].drop_duplicates().copy()
    rows["channel"] = rows["channel"].astype(str)

    spend_source = "channel_total_spend"
    if "channel_total_spend" in run_df.columns:
        spend_df = (
            run_df[["channel", "channel_total_spend"]]
            .assign(channel_total_spend=pd.to_numeric(run_df["channel_total_spend"], errors="coerce"))
            .dropna(subset=["channel_total_spend"])
            .groupby("channel", as_index=False)["channel_total_spend"]
            .median()
        )
        rows = rows.merge(spend_df, on="channel", how="left")
    else:
        rows["channel_total_spend"] = np.nan

    if rows["channel_total_spend"].isna().any():
        data_csv = Path("data/raw/monthly_mocha.csv")
        if data_csv.exists():
            raw = pd.read_csv(data_csv)
            spend_fallback = {}
            for ch in rows["channel"].tolist():
                col = f"{ch}_spend"
                if col in raw.columns:
                    spend_fallback[ch] = float(pd.to_numeric(raw[col], errors="coerce").fillna(0).sum())
            if spend_fallback:
                rows["channel_total_spend"] = rows.apply(
                    lambda r: spend_fallback.get(r["channel"], r["channel_total_spend"]),
                    axis=1,
                )
                spend_source = "raw_monthly_mocha_total_spend"

    effect_source = None
    if "incremental_value_new" in run_df.columns:
        eff_df = (
            run_df[["channel", "incremental_value_new"]]
            .assign(incremental_value_new=pd.to_numeric(run_df["incremental_value_new"], errors="coerce"))
            .groupby("channel", as_index=False)["incremental_value_new"]
            .median()
        )
        rows = rows.merge(eff_df, on="channel", how="left")
        rows["effect_raw"] = rows["incremental_value_new"]
        effect_source = "incremental_value_new"
    elif "incremental_outcome_new" in run_df.columns:
        eff_df = (
            run_df[["channel", "incremental_outcome_new"]]
            .assign(incremental_outcome_new=pd.to_numeric(run_df["incremental_outcome_new"], errors="coerce"))
            .groupby("channel", as_index=False)["incremental_outcome_new"]
            .median()
        )
        rows = rows.merge(eff_df, on="channel", how="left")
        rows["effect_raw"] = rows["incremental_outcome_new"]
        effect_source = "incremental_outcome_new"
    elif {"estimated_roi", "channel_total_spend"}.issubset(run_df.columns):
        tmp = run_df.copy()
        tmp["estimated_roi"] = pd.to_numeric(tmp["estimated_roi"], errors="coerce")
        tmp["channel_total_spend"] = pd.to_numeric(tmp["channel_total_spend"], errors="coerce")
        tmp["effect_proxy"] = tmp["estimated_roi"] * tmp["channel_total_spend"]
        eff_df = tmp.groupby("channel", as_index=False)["effect_proxy"].median()
        rows = rows.merge(eff_df, on="channel", how="left")
        rows["effect_raw"] = rows["effect_proxy"]
        effect_source = "estimated_roi * channel_total_spend"
    else:
        return {"available": False, "reason": "No effect columns found for spend-vs-effect table."}

    if "estimated_roi" in run_df.columns:
        roi_df = (
            run_df[["channel", "estimated_roi"]]
            .assign(estimated_roi=pd.to_numeric(run_df["estimated_roi"], errors="coerce"))
            .groupby("channel", as_index=False)["estimated_roi"]
            .median()
        )
        rows = rows.merge(roi_df, on="channel", how="left")
    else:
        rows["estimated_roi"] = np.nan

    rows["channel_total_spend"] = pd.to_numeric(rows["channel_total_spend"], errors="coerce")
    rows["effect_raw"] = pd.to_numeric(rows["effect_raw"], errors="coerce")
    rows["estimated_roi"] = pd.to_numeric(rows["estimated_roi"], errors="coerce")

    spend_total = float(rows["channel_total_spend"].sum(skipna=True))
    if not np.isfinite(spend_total) or spend_total <= 0:
        return {"available": False, "reason": "Spend totals unavailable; cannot compute spend share."}

    rows["spend_share"] = rows["channel_total_spend"] / spend_total
    rows["effect_nonneg"] = rows["effect_raw"].clip(lower=0)
    effect_total = float(rows["effect_nonneg"].sum(skipna=True))
    rows["effect_share"] = rows["effect_nonneg"] / effect_total if effect_total > 0 else np.nan

    rows["share_gap_pp"] = 100.0 * (rows["effect_share"] - rows["spend_share"])
    rows["spend_share_pct"] = 100.0 * rows["spend_share"]
    rows["effect_share_pct"] = 100.0 * rows["effect_share"]
    rows["effect_negative"] = rows["effect_raw"] < 0

    table_df = rows[
        [
            "channel",
            "channel_total_spend",
            "effect_raw",
            "estimated_roi",
            "spend_share",
            "effect_share",
            "spend_share_pct",
            "effect_share_pct",
            "share_gap_pp",
            "effect_negative",
        ]
    ].copy()
    table_df = table_df.sort_values("effect_share", ascending=False, na_position="last").reset_index(drop=True)
    table_df.to_csv(tables_dir / "spend_vs_effect_table.csv", index=False)

    max_gap_row = None
    if not table_df["share_gap_pp"].dropna().empty:
        idx = table_df["share_gap_pp"].abs().idxmax()
        max_gap_row = table_df.loc[idx].to_dict()

    return {
        "available": True,
        "selected_run_id": selected_run_id,
        "spend_source": spend_source,
        "effect_source": effect_source,
        "n_channels": int(table_df["channel"].nunique()),
        "n_negative_effect_channels": int(table_df["effect_negative"].sum()),
        "max_gap_row": max_gap_row,
        "table_df": table_df,
    }


def _compute_structural_block(
    merged: pd.DataFrame,
    scenario_snapshot: dict,
    cfg: dict,
    tables_dir: Path,
) -> dict:
    if "run_id" not in merged.columns:
        return {"available": False, "reason": "Missing run_id in report input."}

    run_cols = [
        "run_id",
        "target_channel",
        "roi_prior_mu",
        "roi_prior_sigma",
        "roi_prior_dist",
        "is_baseline",
        "qc_status_code",
        "qc_summary_short",
        *STRUCTURAL_COLS,
    ]
    run_cols = [c for c in run_cols if c in merged.columns]
    run_df = merged[run_cols].drop_duplicates(subset=["run_id"]).copy()
    if run_df.empty:
        return {"available": False, "reason": "No run-level rows available."}

    for col, default in DEFAULT_STRUCTURAL.items():
        if col not in run_df.columns:
            run_df[col] = default

    for col in ["roi_prior_mu", "roi_prior_sigma", "adstock_alpha_m", "saturation_ec_m", "saturation_slope_m"]:
        if col in run_df.columns:
            run_df[col] = pd.to_numeric(run_df[col], errors="coerce")
    if "max_lag" in run_df.columns:
        run_df["max_lag"] = pd.to_numeric(run_df["max_lag"], errors="coerce").round(0)
    if "adstock_decay_spec" in run_df.columns:
        run_df["adstock_decay_spec"] = run_df["adstock_decay_spec"].fillna("geometric").astype(str).str.lower()

    grp = merged.groupby("run_id", dropna=False)
    run_abs_pct = grp["abs_pct_change"].sum(min_count=1).rename("total_abs_pct_change")
    run_n_channels = grp["channel"].nunique().rename("n_channels")
    run_df = run_df.merge(run_abs_pct, on="run_id", how="left")
    run_df = run_df.merge(run_n_channels, on="run_id", how="left")

    if "delta_value" in merged.columns:
        run_abs_value = grp["delta_value"].apply(lambda x: pd.to_numeric(x, errors="coerce").abs().sum()).rename(
            "total_abs_value_change"
        )
        run_df = run_df.merge(run_abs_value, on="run_id", how="left")

    run_df["is_baseline"] = run_df.get("is_baseline", False).map(_to_bool)
    run_df["qc_status_code"] = run_df.get("qc_status_code", pd.Series(["UNKNOWN"] * len(run_df))).map(_status_bucket)
    run_df["struct_profile_id"] = run_df.apply(
        lambda r: _struct_profile_id(
            r.get("adstock_alpha_m"),
            r.get("saturation_ec_m"),
            r.get("saturation_slope_m"),
            r.get("max_lag"),
            r.get("adstock_decay_spec"),
        ),
        axis=1,
    )

    profile_agg = (
        run_df.groupby("struct_profile_id", as_index=False)
        .agg(
            adstock_alpha_m=("adstock_alpha_m", "first"),
            saturation_ec_m=("saturation_ec_m", "first"),
            saturation_slope_m=("saturation_slope_m", "first"),
            max_lag=("max_lag", "first"),
            adstock_decay_spec=("adstock_decay_spec", "first"),
            n_runs=("run_id", "nunique"),
            n_baseline_runs=("is_baseline", "sum"),
            mean_total_abs_pct_change=("total_abs_pct_change", "mean"),
            max_total_abs_pct_change=("total_abs_pct_change", "max"),
        )
        .sort_values("max_total_abs_pct_change", ascending=False, na_position="last")
        .reset_index(drop=True)
    )
    if profile_agg.empty:
        return {"available": False, "reason": "No structural profiles found."}

    adstock_rows: list[dict] = []
    profile_rows: list[dict] = []
    for row in profile_agg.itertuples(index=False):
        alpha = _safe_float(getattr(row, "adstock_alpha_m", None))
        max_lag_val = int(_safe_float(getattr(row, "max_lag", 8)) or 8)
        decay = str(getattr(row, "adstock_decay_spec", "geometric") or "geometric").lower()
        weights = _compute_adstock_weights(alpha=alpha, max_lag=max_lag_val, decay_spec=decay)
        immediate_share = float(weights[0]) if len(weights) else 1.0
        carryover_share = float(1.0 - immediate_share)
        avg_lag = float(np.sum(np.arange(len(weights), dtype=float) * weights))
        half_life = _half_life_from_weights(weights)

        profile_rows.append(
            {
                "struct_profile_id": row.struct_profile_id,
                "adstock_alpha_m": alpha,
                "saturation_ec_m": _safe_float(getattr(row, "saturation_ec_m", None)),
                "saturation_slope_m": _safe_float(getattr(row, "saturation_slope_m", None)),
                "max_lag": max_lag_val,
                "adstock_decay_spec": decay,
                "immediate_share": immediate_share,
                "carryover_share": carryover_share,
                "avg_lag": avg_lag,
                "half_life_lag": half_life,
                "n_runs": int(getattr(row, "n_runs", 0)),
                "n_baseline_runs": int(getattr(row, "n_baseline_runs", 0)),
                "mean_total_abs_pct_change": _safe_float(getattr(row, "mean_total_abs_pct_change", None)),
                "max_total_abs_pct_change": _safe_float(getattr(row, "max_total_abs_pct_change", None)),
            }
        )
        for lag, weight in enumerate(weights):
            adstock_rows.append(
                {
                    "struct_profile_id": row.struct_profile_id,
                    "lag": int(lag),
                    "weight": float(weight),
                    "adstock_alpha_m": alpha,
                    "max_lag": max_lag_val,
                    "adstock_decay_spec": decay,
                }
            )

    profile_df = pd.DataFrame(profile_rows)
    adstock_curve_df = pd.DataFrame(adstock_rows)

    sat_rows: list[dict] = []
    x_grid = np.linspace(0.0, 3.0, 121)
    for row in profile_df.itertuples(index=False):
        ec = _safe_float(row.saturation_ec_m)
        slope = _safe_float(row.saturation_slope_m)
        if ec is None or slope is None or ec <= 0 or slope <= 0:
            continue
        x = x_grid.copy()
        y = (x**slope) / (x**slope + ec**slope)
        dy = (slope * (ec**slope) * np.where(x > 0, x ** (slope - 1), 0.0)) / ((x**slope + ec**slope) ** 2)
        for xi, yi, dyi in zip(x, y, dy):
            sat_rows.append(
                {
                    "struct_profile_id": row.struct_profile_id,
                    "spend_index": float(xi),
                    "response_index": float(yi),
                    "marginal_response": float(dyi),
                    "saturation_ec_m": ec,
                    "saturation_slope_m": slope,
                }
            )
    saturation_curve_df = pd.DataFrame(sat_rows)

    selected_run_id = str(scenario_snapshot.get("selected_run_id", "") or "")
    selected_run_row = run_df[run_df["run_id"].astype(str) == selected_run_id].head(1).copy()
    if selected_run_row.empty:
        non_baseline = run_df.loc[~run_df["is_baseline"]].copy()
        pass_non_baseline = non_baseline.loc[non_baseline["qc_status_code"] == "PASS"].copy()
        pool = pass_non_baseline if not pass_non_baseline.empty else (non_baseline if not non_baseline.empty else run_df)
        pool = pool.sort_values("total_abs_pct_change", ascending=False, na_position="last")
        selected_run_row = pool.head(1).copy()
        selected_run_id = str(selected_run_row.iloc[0]["run_id"]) if not selected_run_row.empty else ""

    carryover_df = pd.DataFrame(columns=["channel", "spend_reference", "immediate_component", "carryover_component"])
    selected_profile = None
    if not selected_run_row.empty:
        selected_profile_id = str(selected_run_row.iloc[0]["struct_profile_id"])
        selected_profile_df = profile_df.loc[profile_df["struct_profile_id"] == selected_profile_id].head(1).copy()
        if not selected_profile_df.empty:
            selected_profile = selected_profile_df.iloc[0].to_dict()
            immediate_share = float(selected_profile_df.iloc[0]["immediate_share"])
            carryover_share = float(selected_profile_df.iloc[0]["carryover_share"])

            run_rows = merged.loc[merged["run_id"].astype(str) == selected_run_id, ["channel"]].drop_duplicates().copy()
            spend_map: dict[str, float] = {}
            if "channel_total_spend" in merged.columns:
                tmp = (
                    merged[["channel", "channel_total_spend"]]
                    .copy()
                    .assign(channel_total_spend=pd.to_numeric(merged["channel_total_spend"], errors="coerce"))
                    .dropna(subset=["channel_total_spend"])
                )
                if not tmp.empty:
                    spend_map = tmp.groupby("channel", as_index=False)["channel_total_spend"].median().set_index("channel")[
                        "channel_total_spend"
                    ].to_dict()

            if not spend_map:
                data_csv = Path("data/raw/monthly_mocha.csv")
                if data_csv.exists():
                    raw = pd.read_csv(data_csv)
                    for ch in run_rows["channel"].astype(str).tolist():
                        col = f"{ch}_spend"
                        if col in raw.columns:
                            spend_map[ch] = float(pd.to_numeric(raw[col], errors="coerce").fillna(0).sum())

            carry_rows = []
            for ch in run_rows["channel"].astype(str).tolist():
                spend_ref = float(spend_map.get(ch, 1.0))
                carry_rows.append(
                    {
                        "channel": ch,
                        "spend_reference": spend_ref,
                        "immediate_component": spend_ref * immediate_share,
                        "carryover_component": spend_ref * carryover_share,
                        "immediate_share": immediate_share,
                        "carryover_share": carryover_share,
                        "struct_profile_id": selected_profile_id,
                        "run_id": selected_run_id,
                    }
                )
            carryover_df = pd.DataFrame(carry_rows).sort_values("spend_reference", ascending=False).reset_index(drop=True)

    run_df.sort_values("total_abs_pct_change", ascending=False, na_position="last").to_csv(
        tables_dir / "structural_run_table.csv",
        index=False,
    )
    profile_df.to_csv(tables_dir / "structural_profile_table.csv", index=False)
    adstock_curve_df.to_csv(tables_dir / "structural_adstock_curve_table.csv", index=False)
    saturation_curve_df.to_csv(tables_dir / "structural_saturation_curve_table.csv", index=False)
    carryover_df.to_csv(tables_dir / "structural_carryover_by_channel.csv", index=False)

    top_runs = int(cfg.get("figures", {}).get("structural_top_runs", 12))
    top_profiles = int(cfg.get("figures", {}).get("structural_top_profiles", 4))
    run_display = (
        run_df.sort_values("total_abs_pct_change", ascending=False, na_position="last")
        .head(top_runs)
        .copy()
        .to_dict(orient="records")
    )
    profile_display = profile_df.head(top_profiles).copy().to_dict(orient="records")

    notes = [
        "Immediate vs carryover shares are derived from normalized adstock decay weights.",
        "Saturation curves are Hill-response index curves over a spend-index range [0, 3].",
    ]
    if selected_profile is not None:
        notes.append(
            f"Carryover decomposition uses selected run {selected_run_id} "
            f"with profile {selected_profile.get('struct_profile_id', 'NA')}."
        )

    return {
        "available": True,
        "run_table_df": run_df,
        "profile_df": profile_df,
        "adstock_curve_df": adstock_curve_df,
        "saturation_curve_df": saturation_curve_df,
        "carryover_df": carryover_df,
        "run_rows": run_display,
        "profile_rows": profile_display,
        "selected_run_id": selected_run_id,
        "selected_profile": selected_profile,
        "notes": notes,
    }

def compute_all_metrics(df: pd.DataFrame, cfg: dict, tables_dir: Path) -> dict:
    tables_dir.mkdir(parents=True, exist_ok=True)
    diagnostics = _compute_diagnostics(df, tables_dir)
    scope = _build_scope_info(df)
    scope["n_channels_before"] = int(df["channel"].nunique())
    scope["n_rows_before"] = int(df.shape[0])
    channel_scope = str(cfg.get("analysis", {}).get("channel_scope", "all")).strip().lower()
    target_tokens = _parse_linked_targets(scope.get("target_sets", []))
    if channel_scope == "targets_only":
        keep = {str(x).strip().lower() for x in target_tokens}
        if keep:
            df = df[df["channel"].astype(str).str.lower().isin(keep)].copy()
            scope["channel_scope"] = "targets_only"
            scope["channel_scope_label"] = "Targets Only"
            scope["note"] += (
                " Reporting scope is restricted to the listed target channels, "
                "even though runs still estimate ROI for all modeled channels."
            )
        else:
            scope["channel_scope"] = "all"
            scope["channel_scope_label"] = "All Modeled Channels"
            scope["note"] += " Channel-scope filter was skipped because no target channels were parsed."
    else:
        scope["channel_scope"] = "all"
        scope["channel_scope_label"] = "All Modeled Channels"

    if df.empty:
        raise ValueError("No rows left for report after applying channel scope filter.")
    scope["n_channels_after"] = int(df["channel"].nunique())
    scope["n_rows_after"] = int(df.shape[0])

    baseline_rule = cfg["baseline"]["rule"]

    baselines = []
    for (channel, dist), g in df.groupby(["channel", "roi_prior_dist"], as_index=False):
        mu0, s0 = _pick_baseline(g, baseline_rule)

        g2 = g.assign(d=(g["roi_prior_mu"] - mu0).abs() + (g["roi_prior_sigma"] - s0).abs()).sort_values("d")

        baseline_roi = float(g2.iloc[0]["estimated_roi"])
        baselines.append(
            {
                "channel": channel,
                "roi_prior_dist": dist,
                "baseline_mu": mu0,
                "baseline_sigma": s0,
                "baseline_roi": baseline_roi,
            }
        )

    baseline_df = pd.DataFrame(baselines)

    merged = df.merge(baseline_df, on=["channel", "roi_prior_dist"], how="left")
    pct_source = "median_grid_baseline"

    # Always compute a robust fallback from the report baseline table first.
    # This keeps baseline/non-baseline runs usable even when tornado columns have gaps.
    fallback_baseline = pd.to_numeric(merged["baseline_roi"], errors="coerce")
    fallback_estimated = pd.to_numeric(merged["estimated_roi"], errors="coerce")
    fallback_safe = fallback_baseline.abs() >= 1e-9
    merged["pct_change"] = np.where(
        fallback_safe,
        100.0 * (fallback_estimated - fallback_baseline) / fallback_baseline,
        np.nan,
    )
    merged["baseline_roi_for_rank"] = fallback_baseline

    # Prefer tornado ROI columns when available, but only row-wise where valid.
    if {"roi_baseline", "roi_new"}.issubset(merged.columns):
        tb = pd.to_numeric(merged["roi_baseline"], errors="coerce")
        tn = pd.to_numeric(merged["roi_new"], errors="coerce")
        valid_tb = tb.notna()
        valid_pct = valid_tb & tn.notna() & (tb.abs() >= 1e-9)
        if valid_tb.any():
            merged.loc[valid_tb, "baseline_roi_for_rank"] = tb.loc[valid_tb]
        if valid_pct.any():
            merged.loc[valid_pct, "pct_change"] = (
                100.0 * (tn.loc[valid_pct] - tb.loc[valid_pct]) / tb.loc[valid_pct]
            )
            pct_source = "tornado_roi_columns_with_fallback"
    merged["abs_pct_change"] = merged["pct_change"].abs()
    dollar = _compute_dollar_sensitivity(merged, cfg, tables_dir)
    scenario_snapshot = _compute_scenario_snapshot(merged, cfg, tables_dir)
    spend_effect = _compute_spend_effect_onepager(merged, scenario_snapshot, tables_dir)
    structural = _compute_structural_block(merged, scenario_snapshot, cfg, tables_dir)
    qc_gate = _compute_qc_gate(df, merged, cfg, tables_dir)

    rank = (
        merged.groupby(["channel", "roi_prior_dist"], as_index=False)
        .agg(
            max_abs_pct_change=("abs_pct_change", "max"),
            baseline_roi=("baseline_roi_for_rank", "median"),
            baseline_mu=("baseline_mu", "first"),
            baseline_sigma=("baseline_sigma", "first"),
        )
        .sort_values("max_abs_pct_change", ascending=False)
        .reset_index(drop=True)
    )

    top_n = int(cfg["ranking"]["top_n"])
    rank_top = rank.head(top_n).copy()

    quick_n = min(3, len(rank))
    quick = rank.head(quick_n).copy()
    quick_overview_lines: list[str] = []
    for r in quick.itertuples(index=False):
        quick_overview_lines.append(
            f"{r.channel} ROI prior ({r.roi_prior_dist}): "
            f"max |% change| -> {r.max_abs_pct_change:.2f}% change in estimated ROI"
        )

    hi = float(cfg["thresholds"]["high_sensitivity_pct"])
    med = float(cfg["thresholds"]["medium_sensitivity_pct"])
    recs: list[str] = []
    if (rank["max_abs_pct_change"] >= hi).any():
        worst = rank.iloc[0]
        recs.append(
            f"High sensitivity detected (>= {hi:.1f}%): prioritize better priors/experiments for "
            f"{worst['channel']} ({worst['roi_prior_dist']})."
        )
    if not recs:
        recs.append(f"Overall robust: no channel exceeded {hi:.1f}% max |% change| across tested priors.")
    if (rank["max_abs_pct_change"] >= med).sum() > 1:
        recs.append(
            f"Multiple moderately sensitive channels (>= {med:.1f}%): consider narrowing prior ranges "
            f"or adding holdout validation."
        )

    overview = {
        "n_rows": int(df.shape[0]),
        "n_target_sets": int(df["target_channel"].nunique()),
        "n_channels": int(df["channel"].nunique()),
        "n_dists": int(df["roi_prior_dist"].nunique()),
        "pct_source": pct_source,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    baseline_df.to_csv(tables_dir / "baseline_table.csv", index=False)
    rank.to_csv(tables_dir / "sensitivity_rank.csv", index=False)
    merged.to_csv(tables_dir / "merged_with_pct_change.csv", index=False)

    return {
        "overview": overview,
        "scope": scope,
        "diagnostics": diagnostics,
        "dollar": dollar,
        "scenario_snapshot": scenario_snapshot,
        "spend_effect": spend_effect,
        "structural": structural,
        "qc_gate": qc_gate,
        "baseline_df": baseline_df,
        "rank_df": rank,
        "rank_top_df": rank_top,
        "merged_df": merged,
        "recommendations": recs,
        "quick_overview_lines": quick_overview_lines,
    }












