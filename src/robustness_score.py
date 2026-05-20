import argparse
import os
import subprocess
import sys
from typing import Iterable

import numpy as np
import pandas as pd

from src.baseline_utils import require_explicit_baseline_rows
from src.output_paths import run_csv_path, tables_tag_dir, tornado_csv_path

EPS = 1e-8
MIN_ABS_BASELINE_ROI = 0.05
ELASTICITY_CAP = 10.0
ELASTICITY_REFERENCE = 1.0
DATA_REFERENCE = 1.0
CROSS_REFERENCE = 0.25
DIST_CHANGE_PENALTY = 1.0
BAND_METHOD = "provisional_fixed_thresholds"
RELATIVE_RANK_METHOD = "score_rank_within_current_run"


def _absolute_band(score) -> str:
    if pd.isna(score):
        return ""
    value = float(score)
    if value >= 75.0:
        return "High"
    if value >= 50.0:
        return "Medium"
    return "Low"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("targets", nargs="+", help="Target channel set used for the sensitivity run.")
    parser.add_argument(
        "--include-fail",
        action="store_true",
        help="Include FAIL runs in robustness scoring. Default excludes FAIL runs.",
    )
    parser.add_argument(
        "--overall-weighting",
        choices=["spend", "equal"],
        default="spend",
        help="Weighting for overall model robustness score. Default: spend.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Optional output directory. Defaults to data/output/02_tables/<tag>/.",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Optional output tag to read/write instead of the target-derived tag.",
    )
    return parser


def _tag_for_targets(targets: Iterable[str]) -> str:
    return "_".join(sorted(str(t) for t in targets))


def _sanitize_tag_token(raw: str) -> str:
    s = str(raw).strip().lower()
    out = []
    for ch in s:
        if ch.isalnum() or ch in {"-", "_"}:
            out.append(ch)
        else:
            out.append("_")
    token = "".join(out).strip("_")
    while "__" in token:
        token = token.replace("__", "_")
    return token or "dataset"


def _paths_for_tag(tag: str) -> dict[str, str]:
    return {
        "tornado_csv": str(tornado_csv_path(tag)),
        "run_csv": str(run_csv_path(tag)),
    }


def _ensure_tornado_exists(project_root: str, targets_sorted: list[str], tornado_csv: str) -> str:
    if os.path.exists(tornado_csv):
        return tornado_csv
    os.makedirs(os.path.dirname(tornado_csv), exist_ok=True)

    cmd = [sys.executable, "-m", "src.summarize_sensitivity"] + targets_sorted
    print("Tornado summary missing; building it first.")
    proc = subprocess.run(cmd, cwd=project_root)
    if proc.returncode != 0:
        raise RuntimeError(f"Auto-run of src.summarize_sensitivity failed with exit code {proc.returncode}")

    if not os.path.exists(tornado_csv):
        raise FileNotFoundError(f"Expected tornado CSV still not found: {tornado_csv}")
    return tornado_csv


def _pick_run_csv(run_csv: str) -> str | None:
    if not os.path.exists(run_csv):
        return None
    return run_csv


def _parse_flagged_channels(raw_value) -> set[str]:
    if pd.isna(raw_value):
        return set()
    out = set()
    for token in str(raw_value).split(","):
        token = token.strip()
        if token:
            out.add(token)
    return out


def _rowwise_mean(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    valid_cols = [c for c in cols if c in df.columns]
    if not valid_cols:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return df[valid_cols].apply(lambda row: float(np.nanmean(row.values.astype(float))) if np.isfinite(row.values.astype(float)).any() else np.nan, axis=1)


def _score_from_fragility(value, reference: float = 1.0, cap: float | None = None) -> float:
    if pd.isna(value):
        return float("nan")
    x = max(float(value), 0.0)
    if cap is not None:
        x = min(x, float(cap))
    return float(100.0 / (1.0 + x / max(float(reference), EPS)))


def _score_from_distance(value, reference: float = 1.0) -> float:
    if pd.isna(value):
        return float("nan")
    x = max(float(value), 0.0)
    return float(100.0 * x / (x + max(float(reference), EPS)))


def _mean_available(values: Iterable[float]) -> float:
    vals = [float(v) for v in values if pd.notna(v) and np.isfinite(float(v))]
    return float(np.mean(vals)) if vals else float("nan")


def _median_available(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    return float(vals.median()) if not vals.empty else float("nan")


def _first_existing_col(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    for col in candidates:
        if col in df.columns:
            return df[col]
    return pd.Series(np.nan, index=df.index)


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    v = pd.to_numeric(values, errors="coerce")
    w = pd.to_numeric(weights, errors="coerce").fillna(0)
    mask = v.notna() & w.notna() & (w > 0)
    if mask.sum() == 0:
        return float(v.dropna().mean()) if v.dropna().size else float("nan")
    return float(np.average(v[mask], weights=w[mask]))


def _safe_csv_write(df: pd.DataFrame, path: str) -> str:
    try:
        df.to_csv(path, index=False)
        return path
    except PermissionError:
        base, ext = os.path.splitext(path)
        fallback = f"{base}_locked_{pd.Timestamp.now(tz='UTC').strftime('%Y%m%dT%H%M%SZ')}{ext}"
        df.to_csv(fallback, index=False)
        return fallback


def _safe_text_write(path: str, content: str) -> str:
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path
    except PermissionError:
        base, ext = os.path.splitext(path)
        fallback = f"{base}_locked_{pd.Timestamp.now(tz='UTC').strftime('%Y%m%dT%H%M%SZ')}{ext}"
        with open(fallback, "w", encoding="utf-8") as f:
            f.write(content)
        return fallback


def _build_run_channel_metrics(
    tornado_df: pd.DataFrame,
    *,
    baseline_mu: float,
    baseline_sigma: float,
    baseline_dist: str,
    target_set: set[str],
) -> pd.DataFrame:
    df = tornado_df.copy()

    df["target_channel"] = _first_existing_col(df, ["target_channel", "target_channels", "targets"]).astype(str).str.strip()
    df["channel"] = df["channel"].astype(str).str.strip()
    df["is_target_channel"] = df["target_channel"].astype(str).eq(df["channel"].astype(str))

    roi_baseline = pd.to_numeric(df["roi_baseline"], errors="coerce")
    roi_new = pd.to_numeric(df["roi_new"], errors="coerce")
    roi_delta = roi_new - roi_baseline
    roi_baseline_reliable = roi_baseline.abs() >= MIN_ABS_BASELINE_ROI
    df["roi_change_pct"] = np.where(roi_baseline_reliable, roi_delta.abs() / roi_baseline.abs(), np.nan)
    df["roi_change_signed_pct"] = np.where(roi_baseline_reliable, roi_delta / roi_baseline.abs(), np.nan)
    df["roi_change_pct_unreliable_baseline"] = ~roi_baseline_reliable

    if {"incremental_outcome_new", "incremental_outcome_baseline"}.issubset(df.columns):
        contrib_baseline = pd.to_numeric(df["incremental_outcome_baseline"], errors="coerce")
        contrib_new = pd.to_numeric(df["incremental_outcome_new"], errors="coerce")
        contrib_delta = contrib_new - contrib_baseline
        contrib_reliable = contrib_baseline.abs() >= EPS
        df["contribution_change_pct"] = (
            np.where(contrib_reliable, contrib_delta.abs() / contrib_baseline.abs(), np.nan)
        )
        df["contribution_change_signed_pct"] = (
            np.where(contrib_reliable, contrib_delta / contrib_baseline.abs(), np.nan)
        )
    else:
        df["contribution_change_pct"] = np.nan
        df["contribution_change_signed_pct"] = np.nan

    df["output_change_pct"] = _rowwise_mean(df, ["roi_change_pct", "contribution_change_pct"])
    df["signed_output_change_pct"] = _rowwise_mean(df, ["roi_change_signed_pct", "contribution_change_signed_pct"])

    roi_scale_by_channel = (
        roi_baseline.abs()
        .where(roi_baseline_reliable)
        .groupby(df["channel"].astype(str))
        .median()
        .replace(0, np.nan)
    )
    global_roi_scale = float(roi_baseline.abs().where(roi_baseline.abs() >= MIN_ABS_BASELINE_ROI).median())
    if not np.isfinite(global_roi_scale):
        global_roi_scale = 1.0
    row_roi_scale = df["channel"].astype(str).map(roi_scale_by_channel).fillna(global_roi_scale).clip(lower=EPS)
    df["output_change_delta_fallback"] = np.log1p(roi_delta.abs() / row_roi_scale)
    df["output_change"] = pd.to_numeric(df["output_change_pct"], errors="coerce").combine_first(df["output_change_delta_fallback"])
    df["output_change_method"] = np.where(
        pd.to_numeric(df["output_change_pct"], errors="coerce").notna(),
        "percent_roi_or_contribution",
        "log_scaled_delta_roi",
    )

    df["input_mu_pct"] = (pd.to_numeric(df["roi_prior_mu"], errors="coerce") / max(abs(baseline_mu), EPS) - 1.0).abs()
    df["input_sigma_pct"] = (pd.to_numeric(df["roi_prior_sigma"], errors="coerce") / max(abs(baseline_sigma), EPS) - 1.0).abs()
    df["input_dist_change"] = df["roi_prior_dist"].astype(str).ne(str(baseline_dist)).astype(int)

    df["mu_only"] = (
        (df["input_mu_pct"] > 0)
        & np.isclose(df["input_sigma_pct"], 0.0, atol=1e-12)
        & (df["input_dist_change"] == 0)
    )
    df["sigma_only"] = (
        (df["input_sigma_pct"] > 0)
        & np.isclose(df["input_mu_pct"], 0.0, atol=1e-12)
        & (df["input_dist_change"] == 0)
    )
    df["dist_only"] = (
        (df["input_dist_change"] == 1)
        & np.isclose(df["input_mu_pct"], 0.0, atol=1e-12)
        & np.isclose(df["input_sigma_pct"], 0.0, atol=1e-12)
    )
    df["input_change"] = df["input_mu_pct"] + df["input_sigma_pct"] + (DIST_CHANGE_PENALTY * df["input_dist_change"])
    df["joint_continuous"] = ((df["input_mu_pct"] > 0) | (df["input_sigma_pct"] > 0)) & (df["input_dist_change"] == 0)

    df["elasticity_mu"] = np.where(
        df["mu_only"] & (df["input_mu_pct"] > 0),
        df["output_change"] / df["input_mu_pct"].clip(lower=EPS),
        np.nan,
    )
    df["elasticity_sigma"] = np.where(
        df["sigma_only"] & (df["input_sigma_pct"] > 0),
        df["output_change"] / df["input_sigma_pct"].clip(lower=EPS),
        np.nan,
    )
    df["elasticity_joint"] = np.where(
        df["joint_continuous"],
        df["output_change"] / (df["input_mu_pct"] + df["input_sigma_pct"]).clip(lower=EPS),
        np.nan,
    )
    df["elasticity_any"] = np.where(
        df["input_change"] > 0,
        df["output_change"] / df["input_change"].clip(lower=EPS),
        np.nan,
    )
    for col in ["elasticity_mu", "elasticity_sigma", "elasticity_joint", "elasticity_any"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").clip(upper=ELASTICITY_CAP)
    df["dist_sensitivity"] = np.where(df["dist_only"], df["output_change"], np.nan)

    df["in_target_set"] = df["target_channel"].astype(str).isin(target_set)
    df["flagged_this_channel"] = df.apply(
        lambda r: (
            str(r.get("qc_primary_review_check", "")) == "PriorPosteriorShift"
            and str(r.get("channel", "")) in _parse_flagged_channels(r.get("qc_flagged_channels"))
        ),
        axis=1,
    )
    df["sign_flip"] = np.where(
        pd.to_numeric(df["roi_baseline"], errors="coerce").abs() > EPS,
        np.sign(pd.to_numeric(df["roi_new"], errors="coerce")) != np.sign(pd.to_numeric(df["roi_baseline"], errors="coerce")),
        np.nan,
    )
    return df


def _compute_cross_channel_coupling(run_channel_df: pd.DataFrame, target_set: set[str]) -> dict:
    corr_input = run_channel_df.pivot_table(
        index="run_id",
        columns="channel",
        values="signed_output_change_pct",
        aggfunc="mean",
    )
    corr_matrix = corr_input.corr(min_periods=3)

    target_by_run = (
        run_channel_df[run_channel_df["in_target_set"] == True]
        .groupby("run_id", dropna=False)["output_change_pct"]
        .median()
        .rename("target_median_change")
    )
    all_by_run = (
        run_channel_df.groupby(["run_id", "channel"], dropna=False)["output_change_pct"]
        .median()
        .reset_index()
        .merge(target_by_run.reset_index(), on="run_id", how="left")
    )
    all_by_run["spillover_ratio"] = (
        pd.to_numeric(all_by_run["output_change_pct"], errors="coerce")
        / pd.to_numeric(all_by_run["target_median_change"], errors="coerce").clip(lower=EPS)
    )

    coupling = {}
    for channel in run_channel_df["channel"].astype(str).dropna().unique().tolist():
        corr_term = np.nan
        if channel in corr_matrix.index:
            row = corr_matrix.loc[channel].drop(labels=[channel], errors="ignore").dropna()
            if not row.empty:
                corr_term = float(row.abs().mean())

        spill_term = pd.to_numeric(
            all_by_run.loc[all_by_run["channel"].astype(str) == channel, "spillover_ratio"],
            errors="coerce",
        ).median()

        if channel in target_set:
            # Target channels should not be penalized by a self-spillover denominator artifact.
            spill_term = np.nan

        finite_terms = [float(x) for x in (corr_term, spill_term) if pd.notna(x)]
        coupling[channel] = float(np.mean(finite_terms)) if finite_terms else np.nan
    return coupling


def _compute_channel_scores(
    run_channel_df: pd.DataFrame,
    *,
    baseline_mu: float,
    baseline_sigma: float,
    baseline_dist: str,
    target_set: set[str],
) -> pd.DataFrame:
    rows = []

    for target, group in run_channel_df.groupby("target_channel", dropna=False):
        target = str(target)
        if target_set and target not in target_set:
            continue

        self_group = group[group["channel"].astype(str) == target].copy()
        if self_group.empty:
            self_group = group.copy()

        mu_elast = _median_available(self_group.loc[self_group["mu_only"], "elasticity_mu"])
        sigma_elast = _median_available(self_group.loc[self_group["sigma_only"], "elasticity_sigma"])
        joint_elast = _median_available(self_group.loc[self_group["joint_continuous"], "elasticity_joint"])
        any_elast = _median_available(self_group["elasticity_any"])
        dist_shift = _median_available(self_group.loc[self_group["dist_only"], "dist_sensitivity"])

        sens_components = [x for x in [mu_elast, sigma_elast, joint_elast, dist_shift] if pd.notna(x)]
        sensitivity_fragility = float(np.nanmedian(sens_components)) if sens_components else any_elast
        prior_sensitivity_subscore = _score_from_fragility(
            sensitivity_fragility,
            reference=ELASTICITY_REFERENCE,
            cap=ELASTICITY_CAP,
        )
        if pd.isna(prior_sensitivity_subscore):
            prior_sensitivity_subscore = 50.0

        diffuse_rows = self_group[
            np.isclose(pd.to_numeric(self_group["roi_prior_mu"], errors="coerce"), baseline_mu, atol=1e-12)
            & self_group["roi_prior_dist"].astype(str).eq(str(baseline_dist))
            & (pd.to_numeric(self_group["roi_prior_sigma"], errors="coerce") > baseline_sigma + 1e-12)
        ].copy()
        diffuse_shift = np.nan
        if not diffuse_rows.empty:
            sigma_max = pd.to_numeric(diffuse_rows["roi_prior_sigma"], errors="coerce").max()
            diffuse_shift = pd.to_numeric(
                diffuse_rows[pd.to_numeric(diffuse_rows["roi_prior_sigma"], errors="coerce") == sigma_max]["output_change"],
                errors="coerce",
            ).median()

        data_scores = []
        diffuse_score = _score_from_fragility(diffuse_shift, reference=DATA_REFERENCE)
        if pd.notna(diffuse_score):
            data_scores.append(diffuse_score)
        if "prior_posterior_wasserstein" in self_group.columns:
            w1_med = pd.to_numeric(self_group["prior_posterior_wasserstein"], errors="coerce").median()
            if pd.notna(w1_med):
                data_scores.append(_score_from_distance(w1_med, reference=DATA_REFERENCE))
        if "prior_posterior_kl_gaussian" in self_group.columns:
            kl_med = pd.to_numeric(self_group["prior_posterior_kl_gaussian"], errors="coerce").median()
            if pd.notna(kl_med):
                data_scores.append(_score_from_distance(kl_med, reference=DATA_REFERENCE))
        if "ci_overlap_baseline_new" in self_group.columns:
            ci_overlap_med = pd.to_numeric(self_group["ci_overlap_baseline_new"], errors="coerce").median()
            if pd.notna(ci_overlap_med):
                data_scores.append(100.0 * float(np.clip(ci_overlap_med, 0.0, 1.0)))

        data_influence_subscore = _mean_available(data_scores)
        if pd.isna(data_influence_subscore):
            data_influence_subscore = 50.0

        cross_group = group[group["channel"].astype(str) != target].copy()
        cross_channel_fragility = _median_available(cross_group["output_change"]) if not cross_group.empty else 0.0
        max_cross_channel_fragility = (
            float(pd.to_numeric(cross_group["output_change"], errors="coerce").max())
            if not cross_group.empty and pd.to_numeric(cross_group["output_change"], errors="coerce").notna().any()
            else 0.0
        )
        cross_channel_subscore = _score_from_fragility(cross_channel_fragility, reference=CROSS_REFERENCE)
        if pd.isna(cross_channel_subscore):
            cross_channel_subscore = 100.0

        spend_value = (
            pd.to_numeric(self_group["channel_total_spend"], errors="coerce").median()
            if "channel_total_spend" in self_group.columns
            else np.nan
        )
        fallback_used_rate = pd.to_numeric(self_group["roi_change_pct_unreliable_baseline"], errors="coerce").mean()
        n_runs = int(group["run_id"].nunique()) if "run_id" in group.columns else int(len(group))
        n_self_rows = int(len(self_group))
        n_cross_rows = int(len(cross_group))

        rows.append(
            {
                "channel": target,
                "target_channel": target,
                "in_target_set": target in target_set,
                "n_runs_used": n_runs,
                "n_self_rows": n_self_rows,
                "n_cross_rows": n_cross_rows,
                "channel_total_spend": spend_value,
                "sensitivity_mu_elasticity_median": mu_elast,
                "sensitivity_sigma_elasticity_median": sigma_elast,
                "sensitivity_joint_elasticity_median": joint_elast,
                "sensitivity_any_elasticity_median": any_elast,
                "sensitivity_dist_shift_median": dist_shift,
                "sensitivity_fragility": sensitivity_fragility,
                "prior_sensitivity_raw": sensitivity_fragility,
                "prior_sensitivity_subscore": prior_sensitivity_subscore,
                "data_diffuse_shift_median": diffuse_shift,
                "data_influence_raw": data_influence_subscore,
                "data_influence_subscore": data_influence_subscore,
                "cross_channel_fragility": cross_channel_fragility,
                "max_cross_channel_fragility": max_cross_channel_fragility,
                "cross_channel_subscore": cross_channel_subscore,
                "near_zero_baseline_fallback_rate": fallback_used_rate,
                "score_method": "absolute_prior_sensitivity_v1",
                "band_method": BAND_METHOD,
            }
        )

    channel_df = pd.DataFrame(rows)
    if channel_df.empty:
        raise ValueError("No per-channel rows could be computed for robustness scoring.")

    channel_df["overall_channel_robustness_score"] = (
        0.60 * channel_df["prior_sensitivity_subscore"]
        + 0.25 * channel_df["data_influence_subscore"]
        + 0.15 * channel_df["cross_channel_subscore"]
    )
    return channel_df


def _build_overall_score(
    channel_df: pd.DataFrame,
    *,
    targets_str: str,
    n_runs_used: int,
    excluded_fail_runs: bool,
    overall_weighting: str,
    baseline_mu: float,
    baseline_sigma: float,
    baseline_dist: str,
) -> pd.DataFrame:
    weighting_used = overall_weighting
    if overall_weighting == "spend" and "channel_total_spend" in channel_df.columns:
        weights = pd.to_numeric(channel_df["channel_total_spend"], errors="coerce").fillna(0)
        if float(weights.sum()) <= 0:
            weights = pd.Series(1.0, index=channel_df.index)
            weighting_used = "equal"
    else:
        weights = pd.Series(1.0, index=channel_df.index)
        weighting_used = "equal"

    overall_score = _weighted_mean(channel_df["overall_channel_robustness_score"], weights)
    overall_prior_sens = _weighted_mean(channel_df["prior_sensitivity_subscore"], weights)
    overall_data_inf = _weighted_mean(channel_df["data_influence_subscore"], weights)
    overall_cross = _weighted_mean(channel_df["cross_channel_subscore"], weights)
    overall_near_zero_fallback = _weighted_mean(channel_df.get("near_zero_baseline_fallback_rate", pd.Series(np.nan, index=channel_df.index)), weights)

    target_subset_df = channel_df[channel_df["in_target_set"] == True].copy()
    target_subset_score = (
        _weighted_mean(target_subset_df["overall_channel_robustness_score"], target_subset_df["channel_total_spend"])
        if not target_subset_df.empty
        else np.nan
    )

    overall_band = _absolute_band(overall_score)

    overall_df = pd.DataFrame(
        [
            {
                "targets": targets_str,
                "n_channels": int(len(channel_df)),
                "n_runs_used": int(n_runs_used),
                "excluded_fail_runs": bool(excluded_fail_runs),
                "overall_weighting": weighting_used,
                "baseline_mu": baseline_mu,
                "baseline_sigma": baseline_sigma,
                "baseline_dist": baseline_dist,
                "overall_model_robustness_score": overall_score,
                "overall_model_robustness_band": overall_band,
                "absolute_band": overall_band,
                "overall_prior_sensitivity_subscore": overall_prior_sens,
                "overall_data_influence_subscore": overall_data_inf,
                "overall_cross_channel_subscore": overall_cross,
                "target_subset_robustness_score": target_subset_score,
                "empirical_low_cutoff_q33": np.nan,
                "empirical_high_cutoff_q67": np.nan,
                "band_method": BAND_METHOD,
                "absolute_band_method": BAND_METHOD,
                "score_method": "absolute_prior_sensitivity_v1",
                "score_note": (
                    "Project-defined prior sensitivity heuristic, not an official Meridian metric; "
                    "computed conditional on the selected structural profile."
                ),
                "near_zero_baseline_fallback_rate": overall_near_zero_fallback,
                "relative_rank_method": RELATIVE_RANK_METHOD,
            }
        ]
    )
    return overall_df


def _write_report(
    report_path: str,
    *,
    targets_str: str,
    overall_df: pd.DataFrame,
    channel_df: pd.DataFrame,
    baseline_mu: float,
    baseline_sigma: float,
    baseline_dist: str,
) -> str:
    row = overall_df.iloc[0]
    top_fragile = channel_df.sort_values("overall_channel_robustness_score", ascending=True).head(min(3, len(channel_df)))
    top_robust = channel_df.sort_values("overall_channel_robustness_score", ascending=False).head(min(3, len(channel_df)))

    lines = []
    lines.append(f"# Robustness Score Report ({targets_str})\n")
    lines.append("## Scope\n")
    lines.append(
        "- Primary scope is prior sensitivity robustness for ROI/contribution outputs under prior perturbations, conditional on the selected structural profile.\n"
        "- This is a project-defined heuristic, not an official Meridian metric.\n"
        "- Subscores include sensitivity elasticity (60%), data influence (25%), and cross-channel spillover (15%).\n"
    )
    lines.append("## Formula Blocks\n")
    lines.append(
        "- Sensitivity elasticity: `(Delta output / |baseline output|) / (Delta prior / |baseline prior|)`\n"
        "- Near-zero baseline ROI uses contribution movement when available, otherwise log-scaled absolute delta ROI fallback.\n"
        "- Fragility metrics map to 0-100 with `100 / (1 + fragility / reference_scale)`; higher is more robust.\n"
        "- Data influence increases when diffuse-prior movement is low, prior-posterior distance is high, or credible-interval overlap is high.\n"
        "- Cross-channel fragility uses non-self channel movement when the selected target channel's prior is perturbed.\n"
        "- Structural settings are fixed context only; no adstock/structural robustness subscore is included.\n"
        "- Main bands use provisional fixed thresholds on the 0-100 score: Low < 50, Medium 50-74, High >= 75.\n"
        "- Relative Rank is reported separately as rank / tested channels; rank 1 is most robust within the current run.\n"
    )
    lines.append("## Overall Model Score\n")
    lines.append(
        f"- Overall robustness score: **{float(row['overall_model_robustness_score']):.2f}** ({row['overall_model_robustness_band']})\n"
        f"- Weighting: `{row['overall_weighting']}`\n"
        f"- Baseline prior: mu={baseline_mu:.6f}, sigma={baseline_sigma:.6f}, dist={baseline_dist}\n"
        f"- Overall sensitivity-elasticity subscore (60%): {float(row['overall_prior_sensitivity_subscore']):.2f}\n"
        f"- Overall data-influence subscore (25%): {float(row['overall_data_influence_subscore']):.2f}\n"
        f"- Overall cross-channel subscore (15%): {float(row['overall_cross_channel_subscore']):.2f}\n"
    )
    lines.append("## Most Fragile Channels\n")
    for _, r in top_fragile.iterrows():
        lines.append(
            f"- {r['channel']}: overall={float(r['overall_channel_robustness_score']):.2f}, "
            f"prior_sens={float(r['prior_sensitivity_subscore']):.2f}, "
            f"data_influence={float(r['data_influence_subscore']):.2f}, "
            f"cross_channel={float(r['cross_channel_subscore']):.2f}"
        )
    lines.append("\n## Most Robust Channels\n")
    for _, r in top_robust.iterrows():
        lines.append(
            f"- {r['channel']}: overall={float(r['overall_channel_robustness_score']):.2f}, "
            f"prior_sens={float(r['prior_sensitivity_subscore']):.2f}, "
            f"data_influence={float(r['data_influence_subscore']):.2f}, "
            f"cross_channel={float(r['cross_channel_subscore']):.2f}"
        )

    return _safe_text_write(report_path, "\n".join(lines) + "\n")


def _write_placeholder_outputs(
    *,
    out_dir: str,
    tag: str,
    targets_str: str,
    overall_weighting: str,
    reason: str,
    n_runs_used: int = 0,
) -> None:
    os.makedirs(out_dir, exist_ok=True)

    channel_df = pd.DataFrame(
        columns=[
            "channel",
            "target_channel",
            "in_target_set",
            "n_runs_used",
            "n_self_rows",
            "n_cross_rows",
            "channel_total_spend",
            "sensitivity_fragility",
            "prior_sensitivity_subscore",
            "data_diffuse_shift_median",
            "data_influence_subscore",
            "cross_channel_fragility",
            "cross_channel_subscore",
            "near_zero_baseline_fallback_rate",
            "overall_channel_robustness_score",
            "robustness_band",
            "absolute_band",
            "score_method",
            "band_method",
            "relative_rank",
            "relative_rank_total",
            "relative_rank_label",
            "relative_rank_method",
            "targets",
        ]
    )
    overall_df = pd.DataFrame(
        [
            {
                "targets": targets_str,
                "n_channels": 0,
                "n_runs_used": int(n_runs_used),
                "excluded_fail_runs": True,
                "overall_weighting": overall_weighting,
                "baseline_mu": np.nan,
                "baseline_sigma": np.nan,
                "baseline_dist": "",
                "overall_model_robustness_score": np.nan,
                "overall_model_robustness_band": "",
                "absolute_band": "",
                "overall_prior_sensitivity_subscore": np.nan,
                "overall_data_influence_subscore": np.nan,
                "overall_cross_channel_subscore": np.nan,
                "target_subset_robustness_score": np.nan,
                "empirical_low_cutoff_q33": np.nan,
                "empirical_high_cutoff_q67": np.nan,
                "band_method": BAND_METHOD,
                "absolute_band_method": BAND_METHOD,
                "score_method": "absolute_prior_sensitivity_v1",
                "score_note": reason,
                "near_zero_baseline_fallback_rate": np.nan,
                "relative_rank_method": RELATIVE_RANK_METHOD,
            }
        ]
    )
    run_diag_df = pd.DataFrame()

    channel_csv = os.path.join(out_dir, f"robustness_channel_{tag}.csv")
    overall_csv = os.path.join(out_dir, f"robustness_model_{tag}.csv")
    run_diag_csv = os.path.join(out_dir, f"robustness_run_channel_metrics_{tag}.csv")
    report_path = os.path.join(out_dir, f"robustness_report_{tag}.md")

    _safe_csv_write(channel_df, channel_csv)
    _safe_csv_write(overall_df, overall_csv)
    _safe_csv_write(run_diag_df, run_diag_csv)
    _safe_text_write(
        report_path,
        "\n".join(
            [
                f"# Robustness Score Report ({targets_str})",
                "",
                "Robustness scoring was skipped for this run.",
                "",
                f"Reason: {reason}",
            ]
        )
        + "\n",
    )


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    targets_sorted = sorted(str(t) for t in args.targets)
    if not targets_sorted:
        raise ValueError("Provide at least one target channel.")
    targets_str = ",".join(targets_sorted)
    target_set = set(targets_sorted)
    tag = _sanitize_tag_token(args.tag) if args.tag else _tag_for_targets(targets_sorted)
    out_dir = args.out_dir or str(tables_tag_dir(tag))

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths = _paths_for_tag(tag)
    tornado_csv = _ensure_tornado_exists(project_root, targets_sorted, paths["tornado_csv"])

    tornado_df = pd.read_csv(tornado_csv)
    if tornado_df.empty:
        run_df = pd.DataFrame()
        run_csv = _pick_run_csv(paths["run_csv"])
        if run_csv is not None and os.path.exists(run_csv):
            run_df = pd.read_csv(run_csv)
            if "targets" in run_df.columns:
                run_df = run_df[run_df["targets"].astype(str) == targets_str].copy()
        _write_placeholder_outputs(
            out_dir=out_dir,
            tag=tag,
            targets_str=targets_str,
            overall_weighting=args.overall_weighting,
            reason="No non-baseline tornado rows were available; this is expected for baseline-only structural sweeps.",
            n_runs_used=int(run_df["run_id"].nunique()) if "run_id" in run_df.columns else 0,
        )
        print("Robustness scoring skipped: no tornado rows available for this sweep design.")
        return
    if "targets" in tornado_df.columns:
        targets_col = tornado_df["targets"].astype(str)
        exact_tornado_df = tornado_df[targets_col == targets_str].copy()
        if exact_tornado_df.empty and len(target_set) > 1:
            tornado_df = tornado_df[targets_col.isin(target_set)].copy()
        else:
            tornado_df = exact_tornado_df
    if tornado_df.empty:
        _write_placeholder_outputs(
            out_dir=out_dir,
            tag=tag,
            targets_str=targets_str,
            overall_weighting=args.overall_weighting,
            reason="No tornado rows matched the requested target set.",
            n_runs_used=0,
        )
        print("Robustness scoring skipped: no target-matched tornado rows.")
        return

    run_df = pd.DataFrame()
    run_csv = _pick_run_csv(paths["run_csv"])
    if run_csv is not None and os.path.exists(run_csv):
        run_df = pd.read_csv(run_csv)
        if "targets" in run_df.columns:
            targets_col = run_df["targets"].astype(str)
            exact_run_df = run_df[targets_col == targets_str].copy()
            if exact_run_df.empty and len(target_set) > 1:
                run_df = run_df[targets_col.isin(target_set)].copy()
            else:
                run_df = exact_run_df
        run_meta_cols = [
            c
            for c in ["run_id", "roi_prior_mu", "roi_prior_sigma", "roi_prior_dist", "is_baseline"]
            if c in run_df.columns
        ]
        if run_meta_cols:
            run_meta = run_df[run_meta_cols].drop_duplicates(subset=["run_id"])
            tornado_df = tornado_df.merge(run_meta, on="run_id", how="left", suffixes=("", "_run"))
            for c in ["roi_prior_mu", "roi_prior_sigma", "roi_prior_dist", "is_baseline"]:
                run_col = f"{c}_run"
                if run_col in tornado_df.columns:
                    tornado_df[c] = tornado_df[c].combine_first(tornado_df[run_col])
                    tornado_df = tornado_df.drop(columns=[run_col])

    if not args.include_fail and "qc_status_code" in tornado_df.columns:
        tornado_df = tornado_df[tornado_df["qc_status_code"].astype(str) != "FAIL"].copy()
    if tornado_df.empty:
        _write_placeholder_outputs(
            out_dir=out_dir,
            tag=tag,
            targets_str=targets_str,
            overall_weighting=args.overall_weighting,
            reason="No tornado rows remained after QC filtering.",
            n_runs_used=int(run_df["run_id"].nunique()) if "run_id" in run_df.columns else 0,
        )
        print("Robustness scoring skipped: no rows remained after QC filtering.")
        return

    numeric_cols = [
        "roi_prior_mu",
        "roi_prior_sigma",
        "roi_baseline",
        "roi_new",
        "roi_new_sd",
        "channel_total_spend",
        "incremental_outcome_baseline",
        "incremental_outcome_new",
        "prior_posterior_kl_gaussian",
        "prior_posterior_wasserstein",
        "ci_overlap_baseline_new",
    ]
    for c in numeric_cols:
        if c in tornado_df.columns:
            tornado_df[c] = pd.to_numeric(tornado_df[c], errors="coerce")

    require_explicit_baseline_rows(run_df, context="Run CSV used for robustness scoring")

    baseline_mu = baseline_sigma = baseline_dist = None
    if not run_df.empty and {"is_baseline", "roi_prior_mu", "roi_prior_sigma", "roi_prior_dist"}.issubset(run_df.columns):
        baseline_mask = run_df["is_baseline"].astype(str).str.lower().isin({"true", "1", "yes"})
        baseline_rows = run_df[baseline_mask].copy()
        if not baseline_rows.empty:
            baseline_mu = float(pd.to_numeric(baseline_rows["roi_prior_mu"], errors="coerce").median())
            baseline_sigma = float(pd.to_numeric(baseline_rows["roi_prior_sigma"], errors="coerce").median())
            baseline_dist = str(baseline_rows["roi_prior_dist"].dropna().astype(str).mode().iloc[0])
    if baseline_mu is None or baseline_sigma is None or baseline_dist is None:
        raise ValueError(
            "Explicit baseline metadata is required. No valid is_baseline row was found. "
            "Please regenerate the run/report with an explicit setup-confirmed baseline."
        )

    run_channel_df = _build_run_channel_metrics(
        tornado_df,
        baseline_mu=baseline_mu,
        baseline_sigma=baseline_sigma,
        baseline_dist=baseline_dist,
        target_set=target_set,
    )
    channel_df = _compute_channel_scores(
        run_channel_df,
        baseline_mu=baseline_mu,
        baseline_sigma=baseline_sigma,
        baseline_dist=baseline_dist,
        target_set=target_set,
    )

    channel_df = channel_df.sort_values("overall_channel_robustness_score", ascending=False).reset_index(drop=True)
    channel_df["relative_rank"] = (
        channel_df["overall_channel_robustness_score"]
        .rank(method="min", ascending=False)
        .astype(int)
    )
    channel_df["relative_rank_total"] = int(len(channel_df))
    channel_df["relative_rank_label"] = channel_df["relative_rank"].astype(str) + " / " + str(len(channel_df)) + " tested channels"
    channel_df["relative_rank_method"] = RELATIVE_RANK_METHOD
    channel_df["absolute_band"] = channel_df["overall_channel_robustness_score"].map(_absolute_band)
    channel_df["robustness_band"] = channel_df["absolute_band"]
    channel_df["band_method"] = BAND_METHOD

    overall_df = _build_overall_score(
        channel_df,
        targets_str=targets_str,
        n_runs_used=int(run_channel_df["run_id"].nunique()),
        excluded_fail_runs=bool(not args.include_fail),
        overall_weighting=args.overall_weighting,
        baseline_mu=baseline_mu,
        baseline_sigma=baseline_sigma,
        baseline_dist=baseline_dist,
    )

    channel_df["targets"] = targets_str
    channel_df = channel_df.sort_values("overall_channel_robustness_score", ascending=True).reset_index(drop=True)

    os.makedirs(out_dir, exist_ok=True)

    channel_csv = os.path.join(out_dir, f"robustness_channel_{tag}.csv")
    overall_csv = os.path.join(out_dir, f"robustness_model_{tag}.csv")
    run_diag_csv = os.path.join(out_dir, f"robustness_run_channel_metrics_{tag}.csv")
    report_path = os.path.join(out_dir, f"robustness_report_{tag}.md")

    channel_csv = _safe_csv_write(channel_df, channel_csv)
    overall_csv = _safe_csv_write(overall_df, overall_csv)
    run_diag_csv = _safe_csv_write(run_channel_df, run_diag_csv)
    report_path = _write_report(
        report_path,
        targets_str=targets_str,
        overall_df=overall_df,
        channel_df=channel_df,
        baseline_mu=baseline_mu,
        baseline_sigma=baseline_sigma,
        baseline_dist=baseline_dist,
    )

    print("Robustness scoring complete.")


if __name__ == "__main__":
    main()
