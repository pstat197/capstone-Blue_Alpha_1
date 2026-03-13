from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


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
        "baseline_df": baseline_df,
        "rank_df": rank,
        "rank_top_df": rank_top,
        "merged_df": merged,
        "recommendations": recs,
        "quick_overview_lines": quick_overview_lines,
    }
