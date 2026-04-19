import argparse
import os
import subprocess
import sys
from typing import Iterable

import numpy as np
import pandas as pd

from src.output_paths import OUTPUT_ROOT, candidate_run_csv_paths, candidate_tornado_csv_paths, first_existing

EPS = 1e-8


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
        help="Optional output directory. Defaults to data/output/robustness.",
    )
    return parser


def _tag_for_targets(targets: Iterable[str]) -> str:
    return "_".join(sorted(str(t) for t in targets))


def _paths_for_tag(tag: str) -> dict:
    return {
        "tornado_csv_candidates": candidate_tornado_csv_paths(tag),
        "run_csv_candidates": candidate_run_csv_paths(tag),
    }


def _ensure_tornado_exists(project_root: str, targets_sorted: list[str], tornado_candidates: list) -> str:
    existing = first_existing(tornado_candidates)
    if existing is not None:
        return str(existing)

    # Prefer the first candidate path for post-generation existence checks.
    preferred = str(tornado_candidates[0])
    os.makedirs(os.path.dirname(preferred), exist_ok=True)

    cmd = [sys.executable, "-m", "src.summarize_sensitivity"] + targets_sorted
    print("Tornado CSV missing; generating it first via:")
    print(" ".join(cmd))
    proc = subprocess.run(cmd, cwd=project_root)
    if proc.returncode != 0:
        raise RuntimeError(f"Auto-run of src.summarize_sensitivity failed with exit code {proc.returncode}")

    existing = first_existing(tornado_candidates)
    if existing is None:
        raise FileNotFoundError(f"Expected tornado CSV still not found. Tried: {', '.join(str(p) for p in tornado_candidates)}")
    return str(existing)


def _pick_run_csv(run_candidates: list) -> str | None:
    existing = first_existing(run_candidates)
    if existing is None:
        return None
    return str(existing)


def _pick_center(values: pd.Series):
    vals = sorted(pd.Series(values).dropna().unique().tolist())
    if not vals:
        return None
    return vals[len(vals) // 2]


def _infer_baseline_from_grid(df: pd.DataFrame) -> tuple[float, float, str]:
    mu0 = _pick_center(pd.to_numeric(df.get("roi_prior_mu", pd.Series(dtype=float)), errors="coerce"))
    sigma0 = _pick_center(pd.to_numeric(df.get("roi_prior_sigma", pd.Series(dtype=float)), errors="coerce"))
    dists = [str(x) for x in pd.Series(df.get("roi_prior_dist", pd.Series(dtype=object))).dropna().unique().tolist()]
    dist0 = "LogNormal" if "LogNormal" in dists else (_pick_center(pd.Series(dists)) if dists else None)
    if mu0 is None or sigma0 is None or dist0 is None:
        raise ValueError("Could not infer baseline prior parameters from run/tornado metadata.")
    return float(mu0), float(sigma0), str(dist0)


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


def _scaled_rank(raw: pd.Series) -> pd.Series:
    vals = pd.to_numeric(raw, errors="coerce")
    valid = vals.dropna()
    if valid.empty:
        return pd.Series(0.5, index=vals.index, dtype=float)
    if len(valid) == 1:
        out = pd.Series(0.5, index=vals.index, dtype=float)
        out.loc[valid.index] = 0.5
        return out

    ranks = valid.rank(method="average")
    lo = float(ranks.min())
    hi = float(ranks.max())
    if np.isclose(lo, hi):
        scaled_valid = pd.Series(0.5, index=valid.index, dtype=float)
    else:
        scaled_valid = (ranks - lo) / (hi - lo)

    out = pd.Series(0.5, index=vals.index, dtype=float)
    out.loc[scaled_valid.index] = scaled_valid
    return out


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

    df["roi_change_pct"] = (
        (pd.to_numeric(df["roi_new"], errors="coerce") - pd.to_numeric(df["roi_baseline"], errors="coerce")).abs()
        / pd.to_numeric(df["roi_baseline"], errors="coerce").abs().clip(lower=EPS)
    )
    df["roi_change_signed_pct"] = (
        (pd.to_numeric(df["roi_new"], errors="coerce") - pd.to_numeric(df["roi_baseline"], errors="coerce"))
        / pd.to_numeric(df["roi_baseline"], errors="coerce").abs().clip(lower=EPS)
    )

    if {"incremental_outcome_new", "incremental_outcome_baseline"}.issubset(df.columns):
        df["contribution_change_pct"] = (
            (pd.to_numeric(df["incremental_outcome_new"], errors="coerce") - pd.to_numeric(df["incremental_outcome_baseline"], errors="coerce")).abs()
            / pd.to_numeric(df["incremental_outcome_baseline"], errors="coerce").abs().clip(lower=EPS)
        )
        df["contribution_change_signed_pct"] = (
            (pd.to_numeric(df["incremental_outcome_new"], errors="coerce") - pd.to_numeric(df["incremental_outcome_baseline"], errors="coerce"))
            / pd.to_numeric(df["incremental_outcome_baseline"], errors="coerce").abs().clip(lower=EPS)
        )
    else:
        df["contribution_change_pct"] = np.nan
        df["contribution_change_signed_pct"] = np.nan

    # Core output movement uses both ROI and contribution changes when available.
    df["output_change_pct"] = _rowwise_mean(df, ["roi_change_pct", "contribution_change_pct"])
    df["signed_output_change_pct"] = _rowwise_mean(df, ["roi_change_signed_pct", "contribution_change_signed_pct"])

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
    df["joint_continuous"] = ((df["input_mu_pct"] > 0) | (df["input_sigma_pct"] > 0)) & (df["input_dist_change"] == 0)

    df["elasticity_mu"] = np.where(
        df["mu_only"] & (df["input_mu_pct"] > 0),
        df["output_change_pct"] / df["input_mu_pct"].clip(lower=EPS),
        np.nan,
    )
    df["elasticity_sigma"] = np.where(
        df["sigma_only"] & (df["input_sigma_pct"] > 0),
        df["output_change_pct"] / df["input_sigma_pct"].clip(lower=EPS),
        np.nan,
    )
    df["elasticity_joint"] = np.where(
        df["joint_continuous"],
        df["output_change_pct"] / (df["input_mu_pct"] + df["input_sigma_pct"]).clip(lower=EPS),
        np.nan,
    )
    df["dist_sensitivity"] = np.where(df["dist_only"], df["output_change_pct"], np.nan)

    df["in_target_set"] = df["channel"].astype(str).isin(target_set)
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

        coupling[channel] = float(np.nanmean([corr_term, spill_term]))
    return coupling


def _compute_channel_scores(
    run_channel_df: pd.DataFrame,
    *,
    baseline_mu: float,
    baseline_sigma: float,
    baseline_dist: str,
    target_set: set[str],
) -> pd.DataFrame:
    coupling_by_channel = _compute_cross_channel_coupling(run_channel_df, target_set)
    rows = []

    for channel, group in run_channel_df.groupby("channel", dropna=False):
        channel = str(channel)

        mu_elast = pd.to_numeric(group.loc[group["mu_only"], "elasticity_mu"], errors="coerce").median()
        sigma_elast = pd.to_numeric(group.loc[group["sigma_only"], "elasticity_sigma"], errors="coerce").median()
        joint_elast = pd.to_numeric(group.loc[group["joint_continuous"], "elasticity_joint"], errors="coerce").median()
        dist_shift = pd.to_numeric(group.loc[group["dist_only"], "dist_sensitivity"], errors="coerce").median()

        sens_components = [x for x in [mu_elast, sigma_elast, joint_elast, dist_shift] if pd.notna(x)]
        sensitivity_raw = float(np.nanmean(sens_components)) if sens_components else float(
            pd.to_numeric(group["output_change_pct"], errors="coerce").median()
        )

        diffuse_rows = group[
            np.isclose(pd.to_numeric(group["roi_prior_mu"], errors="coerce"), baseline_mu, atol=1e-12)
            & group["roi_prior_dist"].astype(str).eq(str(baseline_dist))
            & (pd.to_numeric(group["roi_prior_sigma"], errors="coerce") > baseline_sigma + 1e-12)
        ].copy()
        diffuse_shift = np.nan
        if not diffuse_rows.empty:
            sigma_max = pd.to_numeric(diffuse_rows["roi_prior_sigma"], errors="coerce").max()
            diffuse_shift = pd.to_numeric(
                diffuse_rows[pd.to_numeric(diffuse_rows["roi_prior_sigma"], errors="coerce") == sigma_max]["output_change_pct"],
                errors="coerce",
            ).median()

        flagged_rate = pd.to_numeric(group["flagged_this_channel"], errors="coerce").mean()
        data_terms = [x for x in [diffuse_shift, flagged_rate] if pd.notna(x)]

        # Prior-posterior distance metrics: larger distance should reduce fragility.
        if "prior_posterior_wasserstein" in group.columns:
            w1_med = pd.to_numeric(group["prior_posterior_wasserstein"], errors="coerce").median()
            if pd.notna(w1_med):
                data_terms.append(1.0 / (1.0 + float(w1_med)))
        if "prior_posterior_kl_gaussian" in group.columns:
            kl_med = pd.to_numeric(group["prior_posterior_kl_gaussian"], errors="coerce").median()
            if pd.notna(kl_med):
                data_terms.append(1.0 / (1.0 + max(float(kl_med), 0.0)))
        if "ci_overlap_baseline_new" in group.columns:
            ci_overlap_med = pd.to_numeric(group["ci_overlap_baseline_new"], errors="coerce").median()
            if pd.notna(ci_overlap_med):
                data_terms.append(1.0 - float(np.clip(ci_overlap_med, 0.0, 1.0)))

        data_influence_raw = float(np.nanmean(data_terms)) if data_terms else float(
            pd.to_numeric(group["output_change_pct"], errors="coerce").median()
        )

        cross_channel_raw = coupling_by_channel.get(channel, np.nan)

        # Adstock proxy: we do not have adstock-parameter perturbations in this experiment.
        # Use sign instability + CI instability + posterior dispersion as a structural proxy.
        sign_flip_rate = pd.to_numeric(group["sign_flip"], errors="coerce").mean()
        ci_instability = np.nan
        if "ci_overlap_baseline_new" in group.columns:
            ci_overlap_med = pd.to_numeric(group["ci_overlap_baseline_new"], errors="coerce").median()
            if pd.notna(ci_overlap_med):
                ci_instability = 1.0 - float(np.clip(ci_overlap_med, 0.0, 1.0))

        dispersion_term = np.nan
        if {"roi_new_sd", "roi_new"}.issubset(group.columns):
            dispersion_term = pd.to_numeric(group["roi_new_sd"], errors="coerce").abs().median() / (
                pd.to_numeric(group["roi_new"], errors="coerce").abs().median() + EPS
            )

        adstock_proxy_raw = float(np.nanmean([sign_flip_rate, ci_instability, dispersion_term]))

        spend_value = (
            pd.to_numeric(group["channel_total_spend"], errors="coerce").median()
            if "channel_total_spend" in group.columns
            else np.nan
        )

        rows.append(
            {
                "channel": channel,
                "in_target_set": channel in target_set,
                "n_runs_used": int(len(group)),
                "channel_total_spend": spend_value,
                "sensitivity_mu_elasticity_median": mu_elast,
                "sensitivity_sigma_elasticity_median": sigma_elast,
                "sensitivity_joint_elasticity_median": joint_elast,
                "sensitivity_dist_shift_median": dist_shift,
                "prior_sensitivity_raw": sensitivity_raw,
                "data_diffuse_shift_median": diffuse_shift,
                "data_prior_shift_flag_rate": flagged_rate,
                "data_influence_raw": data_influence_raw,
                "cross_channel_coupling_raw": cross_channel_raw,
                "adstock_proxy_sign_flip_rate": sign_flip_rate,
                "adstock_proxy_raw": adstock_proxy_raw,
            }
        )

    channel_df = pd.DataFrame(rows)
    if channel_df.empty:
        raise ValueError("No per-channel rows could be computed for robustness scoring.")

    channel_df["prior_sensitivity_fragility_rank"] = _scaled_rank(channel_df["prior_sensitivity_raw"])
    channel_df["data_influence_fragility_rank"] = _scaled_rank(channel_df["data_influence_raw"])
    channel_df["cross_channel_fragility_rank"] = _scaled_rank(channel_df["cross_channel_coupling_raw"])
    channel_df["adstock_proxy_fragility_rank"] = _scaled_rank(channel_df["adstock_proxy_raw"])

    channel_df["prior_sensitivity_subscore"] = 100.0 * (1.0 - channel_df["prior_sensitivity_fragility_rank"])
    channel_df["data_influence_subscore"] = 100.0 * (1.0 - channel_df["data_influence_fragility_rank"])
    channel_df["cross_channel_subscore"] = 100.0 * (1.0 - channel_df["cross_channel_fragility_rank"])
    channel_df["adstock_proxy_subscore"] = 100.0 * (1.0 - channel_df["adstock_proxy_fragility_rank"])

    # Advisor-scoped prior sensitivity is primary; adstock is a secondary proxy here.
    channel_df["overall_channel_robustness_score"] = (
        0.50 * channel_df["prior_sensitivity_subscore"]
        + 0.30 * channel_df["data_influence_subscore"]
        + 0.15 * channel_df["cross_channel_subscore"]
        + 0.05 * channel_df["adstock_proxy_subscore"]
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
) -> tuple[pd.DataFrame, float, float]:
    if overall_weighting == "spend" and "channel_total_spend" in channel_df.columns:
        weights = pd.to_numeric(channel_df["channel_total_spend"], errors="coerce").fillna(0)
        if float(weights.sum()) <= 0:
            weights = pd.Series(1.0, index=channel_df.index)
    else:
        weights = pd.Series(1.0, index=channel_df.index)

    overall_score = _weighted_mean(channel_df["overall_channel_robustness_score"], weights)
    overall_prior_sens = _weighted_mean(channel_df["prior_sensitivity_subscore"], weights)
    overall_data_inf = _weighted_mean(channel_df["data_influence_subscore"], weights)
    overall_cross = _weighted_mean(channel_df["cross_channel_subscore"], weights)
    overall_adstock = _weighted_mean(channel_df["adstock_proxy_subscore"], weights)

    target_subset_df = channel_df[channel_df["in_target_set"] == True].copy()
    target_subset_score = (
        _weighted_mean(target_subset_df["overall_channel_robustness_score"], target_subset_df["channel_total_spend"])
        if not target_subset_df.empty
        else np.nan
    )

    q33 = float(channel_df["overall_channel_robustness_score"].quantile(1.0 / 3.0))
    q67 = float(channel_df["overall_channel_robustness_score"].quantile(2.0 / 3.0))

    overall_band = "Medium"
    if overall_score < q33:
        overall_band = "Low"
    elif overall_score >= q67:
        overall_band = "High"

    overall_df = pd.DataFrame(
        [
            {
                "targets": targets_str,
                "n_channels": int(len(channel_df)),
                "n_runs_used": int(n_runs_used),
                "excluded_fail_runs": bool(excluded_fail_runs),
                "overall_weighting": overall_weighting,
                "baseline_mu": baseline_mu,
                "baseline_sigma": baseline_sigma,
                "baseline_dist": baseline_dist,
                "overall_model_robustness_score": overall_score,
                "overall_model_robustness_band": overall_band,
                "overall_prior_sensitivity_subscore": overall_prior_sens,
                "overall_data_influence_subscore": overall_data_inf,
                "overall_cross_channel_subscore": overall_cross,
                "overall_adstock_proxy_subscore": overall_adstock,
                "target_subset_robustness_score": target_subset_score,
                "empirical_low_cutoff_q33": q33,
                "empirical_high_cutoff_q67": q67,
                "adstock_note": "Proxy-only (no adstock sweep in current experiment design)",
            }
        ]
    )
    return overall_df, q33, q67


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
        "- Primary scope is prior sensitivity robustness for ROI/contribution outputs under prior perturbations.\n"
        "- Subscores include prior sensitivity, data influence, cross-channel coupling, and an adstock proxy stability score.\n"
    )
    lines.append("## Formula Blocks\n")
    lines.append(
        "- Sensitivity elasticity: `(Delta output / |baseline output|) / (Delta prior / |baseline prior|)`\n"
        "- Data influence fragility increases when diffuse-prior runs still shift outputs strongly, flagged prior-posterior-shift rates are high, or prior-posterior distance is small.\n"
        "- Cross-channel fragility increases with mean absolute correlation and spillover ratio across channels.\n"
        "- Adstock proxy fragility increases with sign-flip rate, CI instability, and posterior dispersion (proxy only in current experiment).\n"
    )
    lines.append("## Overall Model Score\n")
    lines.append(
        f"- Overall robustness score: **{float(row['overall_model_robustness_score']):.2f}** ({row['overall_model_robustness_band']})\n"
        f"- Weighting: `{row['overall_weighting']}`\n"
        f"- Baseline prior: mu={baseline_mu:.6f}, sigma={baseline_sigma:.6f}, dist={baseline_dist}\n"
        f"- Overall prior-sensitivity subscore: {float(row['overall_prior_sensitivity_subscore']):.2f}\n"
        f"- Overall data-influence subscore: {float(row['overall_data_influence_subscore']):.2f}\n"
        f"- Overall cross-channel subscore: {float(row['overall_cross_channel_subscore']):.2f}\n"
        f"- Overall adstock proxy subscore: {float(row['overall_adstock_proxy_subscore']):.2f}\n"
    )
    lines.append("## Most Fragile Channels\n")
    for _, r in top_fragile.iterrows():
        lines.append(
            f"- {r['channel']}: overall={float(r['overall_channel_robustness_score']):.2f}, "
            f"prior_sens={float(r['prior_sensitivity_subscore']):.2f}, "
            f"data_influence={float(r['data_influence_subscore']):.2f}, "
            f"cross_channel={float(r['cross_channel_subscore']):.2f}, "
            f"adstock_proxy={float(r['adstock_proxy_subscore']):.2f}"
        )
    lines.append("\n## Most Robust Channels\n")
    for _, r in top_robust.iterrows():
        lines.append(
            f"- {r['channel']}: overall={float(r['overall_channel_robustness_score']):.2f}, "
            f"prior_sens={float(r['prior_sensitivity_subscore']):.2f}, "
            f"data_influence={float(r['data_influence_subscore']):.2f}, "
            f"cross_channel={float(r['cross_channel_subscore']):.2f}, "
            f"adstock_proxy={float(r['adstock_proxy_subscore']):.2f}"
        )

    return _safe_text_write(report_path, "\n".join(lines) + "\n")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    targets_sorted = sorted(str(t) for t in args.targets)
    if not targets_sorted:
        raise ValueError("Provide at least one target channel.")
    targets_str = ",".join(targets_sorted)
    target_set = set(targets_sorted)
    tag = _tag_for_targets(targets_sorted)

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths = _paths_for_tag(tag)
    tornado_csv = _ensure_tornado_exists(project_root, targets_sorted, paths["tornado_csv_candidates"])

    tornado_df = pd.read_csv(tornado_csv)
    if tornado_df.empty:
        raise ValueError(f"Tornado CSV is empty: {tornado_csv}")
    if "targets" in tornado_df.columns:
        tornado_df = tornado_df[tornado_df["targets"].astype(str) == targets_str].copy()
    if tornado_df.empty:
        raise ValueError("No rows found for the requested target set in tornado CSV.")

    run_df = pd.DataFrame()
    run_csv = _pick_run_csv(paths["run_csv_candidates"])
    if run_csv is not None and os.path.exists(run_csv):
        run_df = pd.read_csv(run_csv)
        if "targets" in run_df.columns:
            run_df = run_df[run_df["targets"].astype(str) == targets_str].copy()
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
        raise ValueError("No rows available after QC filtering.")

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

    baseline_mu = baseline_sigma = baseline_dist = None
    if not run_df.empty and {"is_baseline", "roi_prior_mu", "roi_prior_sigma", "roi_prior_dist"}.issubset(run_df.columns):
        baseline_mask = run_df["is_baseline"].astype(str).str.lower().isin({"true", "1", "yes"})
        baseline_rows = run_df[baseline_mask].copy()
        if not baseline_rows.empty:
            baseline_mu = float(pd.to_numeric(baseline_rows["roi_prior_mu"], errors="coerce").median())
            baseline_sigma = float(pd.to_numeric(baseline_rows["roi_prior_sigma"], errors="coerce").median())
            baseline_dist = str(baseline_rows["roi_prior_dist"].dropna().astype(str).mode().iloc[0])
    if baseline_mu is None or baseline_sigma is None or baseline_dist is None:
        baseline_mu, baseline_sigma, baseline_dist = _infer_baseline_from_grid(tornado_df)

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

    overall_df, q33, q67 = _build_overall_score(
        channel_df,
        targets_str=targets_str,
        n_runs_used=int(run_channel_df["run_id"].nunique()),
        excluded_fail_runs=bool(not args.include_fail),
        overall_weighting=args.overall_weighting,
        baseline_mu=baseline_mu,
        baseline_sigma=baseline_sigma,
        baseline_dist=baseline_dist,
    )

    channel_df["robustness_band"] = np.where(
        channel_df["overall_channel_robustness_score"] < q33,
        "Low",
        np.where(channel_df["overall_channel_robustness_score"] < q67, "Medium", "High"),
    )
    channel_df["targets"] = targets_str
    channel_df = channel_df.sort_values("overall_channel_robustness_score", ascending=True).reset_index(drop=True)

    out_dir = args.out_dir or os.path.join(str(OUTPUT_ROOT), "robustness")
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

    print("Saved per-channel robustness scores to:")
    print(channel_csv)
    print("Saved overall model robustness score to:")
    print(overall_csv)
    print("Saved run-level diagnostics to:")
    print(run_diag_csv)
    print("Saved robustness report to:")
    print(report_path)


if __name__ == "__main__":
    main()
