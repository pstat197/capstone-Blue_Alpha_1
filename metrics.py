from __future__ import annotations
from pathlib import Path
import pandas as pd
from datetime import datetime


def _pick_baseline(group: pd.DataFrame, rule: str) -> tuple[float, float]:
    if rule == "median":
        return float(group["roi_prior_mu"].median()), float(group["roi_prior_sigma"].median())
    raise ValueError(f"Unknown baseline rule: {rule}")


def compute_all_metrics(df: pd.DataFrame, cfg: dict, tables_dir: Path) -> dict:
    baseline_rule = cfg["baseline"]["rule"]

    baselines = []
    for (tgt, dist), g in df.groupby(["target_channel", "roi_prior_dist"], as_index=False):
        mu0, s0 = _pick_baseline(g, baseline_rule)

        g2 = g.assign(
            d=(g["roi_prior_mu"] - mu0).abs() + (g["roi_prior_sigma"] - s0).abs()
        ).sort_values("d")

        baseline_roi = float(g2.iloc[0]["estimated_roi"])
        baselines.append(
            {
                "target_channel": tgt,
                "roi_prior_dist": dist,
                "baseline_mu": mu0,
                "baseline_sigma": s0,
                "baseline_roi": baseline_roi,
            }
        )

    baseline_df = pd.DataFrame(baselines)

    merged = df.merge(baseline_df, on=["target_channel", "roi_prior_dist"], how="left")
    merged["pct_change"] = 100.0 * (merged["estimated_roi"] - merged["baseline_roi"]) / merged["baseline_roi"]
    merged["abs_pct_change"] = merged["pct_change"].abs()

    rank = (
        merged.groupby(["target_channel", "roi_prior_dist"], as_index=False)
        .agg(
            max_abs_pct_change=("abs_pct_change", "max"),
            baseline_roi=("baseline_roi", "first"),
            baseline_mu=("baseline_mu", "first"),
            baseline_sigma=("baseline_sigma", "first"),
        )
        .sort_values("max_abs_pct_change", ascending=False)
    )

    top_n = int(cfg["ranking"]["top_n"])
    rank_top = rank.head(top_n).copy()

    quick_n = min(3, len(rank))
    quick = rank.head(quick_n).copy()
    quick_overview_lines: list[str] = []
    for i, r in enumerate(quick.itertuples(index=False), start=1):
        quick_overview_lines.append(
            f"{i}. {r.target_channel} ROI prior ({r.roi_prior_dist}): "
            f"max |% change| → {r.max_abs_pct_change:.2f}% change in estimated ROI"
        )

    hi = float(cfg["thresholds"]["high_sensitivity_pct"])
    med = float(cfg["thresholds"]["medium_sensitivity_pct"])
    recs: list[str] = []
    if (rank["max_abs_pct_change"] >= hi).any():
        worst = rank.iloc[0]
        recs.append(
            f"High sensitivity detected (≥ {hi:.1f}%): prioritize better priors/experiments for "
            f"{worst['target_channel']} ({worst['roi_prior_dist']})."
        )
    if not recs:
        recs.append(f"Overall robust: no target exceeded {hi:.1f}% max |% change| across tested priors.")
    if (rank["max_abs_pct_change"] >= med).sum() > 1:
        recs.append(
            f"Multiple moderately sensitive targets (≥ {med:.1f}%): consider narrowing prior ranges "
            f"or adding holdout validation."
        )

    overview = {
        "n_rows": int(df.shape[0]),
        "n_targets": int(df["target_channel"].nunique()),
        "n_channels": int(df["channel"].nunique()),
        "n_dists": int(df["roi_prior_dist"].nunique()),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    tables_dir.mkdir(parents=True, exist_ok=True)
    baseline_df.to_csv(tables_dir / "baseline_table.csv", index=False)
    rank.to_csv(tables_dir / "sensitivity_rank.csv", index=False)
    merged.to_csv(tables_dir / "merged_with_pct_change.csv", index=False)

    return {
        "overview": overview,
        "baseline_df": baseline_df,
        "rank_df": rank,
        "rank_top_df": rank_top,
        "merged_df": merged,
        "recommendations": recs,
        "quick_overview_lines": quick_overview_lines,
    }