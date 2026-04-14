from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.formatting import status_bucket as _status_bucket
from src.output_paths import (
    PROJECT_ROOT,
    candidate_run_csv_paths,
    candidate_tornado_csv_paths,
    first_existing,
)


DEFAULT_MU_VALUES = [0.020759, 0.051898]
DEFAULT_SIGMA_VALUES = [0.006689, 0.033445]
DEFAULT_DISTS = ["Normal"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a QC gate summary from an existing sensitivity run table.",
    )
    parser.add_argument("targets", nargs="+", help="Linked target channels (e.g., google meta tiktok).")
    parser.add_argument(
        "--mu-values",
        nargs="+",
        type=float,
        default=DEFAULT_MU_VALUES,
        help="Accepted ROI prior mu values for QC gate subset.",
    )
    parser.add_argument(
        "--sigma-values",
        nargs="+",
        type=float,
        default=DEFAULT_SIGMA_VALUES,
        help="Accepted ROI prior sigma values for QC gate subset.",
    )
    parser.add_argument(
        "--dists",
        nargs="+",
        default=DEFAULT_DISTS,
        help="Accepted ROI prior distribution families for QC gate subset.",
    )
    parser.add_argument(
        "--outdir",
        default=None,
        help="Output directory for QC gate artifacts. Defaults to data/output/03_reports/report/<tag>.",
    )
    return parser



# _status_bucket is now imported from src.formatting


def _pick_sensitivity_col(df: pd.DataFrame) -> str | None:
    for col in ["delta_value_abs", "delta_outcome_abs", "delta_abs"]:
        if col in df.columns:
            return col
    return None


def _format_targets(targets: list[str]) -> tuple[list[str], str, str]:
    targets_sorted = sorted(str(t).strip() for t in targets if str(t).strip())
    if not targets_sorted:
        raise ValueError("At least one non-empty target is required.")
    tag = "_".join(targets_sorted)
    targets_csv = ",".join(targets_sorted)
    return targets_sorted, tag, targets_csv


def _find_run_csv(tag: str) -> Path:
    run_csv = first_existing(candidate_run_csv_paths(tag))
    if run_csv is None:
        tried = ", ".join(str(p) for p in candidate_run_csv_paths(tag))
        raise FileNotFoundError(f"Run CSV not found for tag={tag}. Tried: {tried}")
    return run_csv


def _find_tornado_csv(tag: str) -> Path | None:
    return first_existing(candidate_tornado_csv_paths(tag))


def _build_qc_subset(
    run_df: pd.DataFrame,
    targets_csv: str,
    mu_values: list[float],
    sigma_values: list[float],
    dists: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    scope_df = run_df.copy()
    if "targets" in scope_df.columns:
        scope_df = scope_df[scope_df["targets"].astype(str) == targets_csv].copy()

    if scope_df.empty:
        raise ValueError(f"No rows found for targets='{targets_csv}' in run CSV.")

    accepted_mu = {round(float(x), 6) for x in mu_values}
    accepted_sigma = {round(float(x), 6) for x in sigma_values}
    accepted_dists = {str(x).strip() for x in dists}

    scope_df["mu_key"] = pd.to_numeric(scope_df["roi_prior_mu"], errors="coerce").round(6)
    scope_df["sigma_key"] = pd.to_numeric(scope_df["roi_prior_sigma"], errors="coerce").round(6)
    scope_df["dist_key"] = scope_df["roi_prior_dist"].astype(str).str.strip()

    qc_subset = scope_df[
        scope_df["mu_key"].isin(accepted_mu)
        & scope_df["sigma_key"].isin(accepted_sigma)
        & scope_df["dist_key"].isin(accepted_dists)
    ].copy()

    if qc_subset.empty:
        raise ValueError(
            "QC subset is empty. Check --mu-values/--sigma-values/--dists against the run CSV."
        )

    return qc_subset, scope_df


def _build_channel_rank(tornado_csv: Path | None, run_ids: set[str]) -> tuple[pd.DataFrame, str | None]:
    if tornado_csv is None or not tornado_csv.exists():
        return pd.DataFrame(), None

    tor = pd.read_csv(tornado_csv)
    if tor.empty or "run_id" not in tor.columns or "channel" not in tor.columns:
        return pd.DataFrame(), None

    tor = tor[tor["run_id"].astype(str).isin(run_ids)].copy()
    if tor.empty:
        return pd.DataFrame(), None

    metric_col = _pick_sensitivity_col(tor)
    if metric_col is None:
        return pd.DataFrame(), None

    tor[metric_col] = pd.to_numeric(tor[metric_col], errors="coerce")
    rank = (
        tor.groupby("channel", as_index=False)[metric_col]
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
    return rank, metric_col


def _write_markdown(
    out_md: Path,
    *,
    targets_sorted: list[str],
    run_csv: Path,
    tornado_csv: Path | None,
    qc_subset: pd.DataFrame,
    scope_df: pd.DataFrame,
    rank_df: pd.DataFrame,
    rank_metric: str | None,
    table_run_rel: str,
    table_rank_rel: str | None,
) -> None:
    qc = qc_subset.copy()
    qc["status_bucket"] = qc["qc_status_code"].map(_status_bucket)

    n_total_scope = int(scope_df.shape[0])
    n_qc = int(qc.shape[0])
    n_pass = int((qc["status_bucket"] == "PASS").sum())
    n_review = int((qc["status_bucket"] == "REVIEW").sum())
    n_fail = int((qc["status_bucket"] == "FAIL").sum())
    pass_rate = 100.0 * n_pass / float(n_qc) if n_qc else 0.0
    gate_pass = n_fail == 0 and n_review == 0

    outside = scope_df[~scope_df["run_id"].astype(str).isin(set(qc["run_id"].astype(str)))].copy()
    outside["status_bucket"] = outside["qc_status_code"].map(_status_bucket)
    outside_counts = outside["status_bucket"].value_counts().to_dict()

    mean_r2 = pd.to_numeric(qc.get("qc_r2", pd.Series(dtype=float)), errors="coerce").mean()
    mean_mape = pd.to_numeric(qc.get("qc_mape", pd.Series(dtype=float)), errors="coerce").mean()
    mean_wmape = pd.to_numeric(qc.get("qc_wmape", pd.Series(dtype=float)), errors="coerce").mean()
    max_baseline_neg_prob = pd.to_numeric(
        qc.get("qc_baseline_neg_prob", pd.Series(dtype=float)),
        errors="coerce",
    ).max()

    header = []
    header.append(f"# QC Gate Summary ({'_'.join(targets_sorted)})")
    header.append("")
    header.append(f"- Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    header.append(f"- Targets: {', '.join(targets_sorted)}")
    header.append(f"- Source run CSV: `{run_csv}`")
    if tornado_csv is not None:
        header.append(f"- Source tornado CSV: `{tornado_csv}`")
    header.append("")

    gate = []
    gate.append("## Gate Decision")
    gate.append("")
    gate.append(f"- Result: **{'PASS' if gate_pass else 'REVIEW'}**")
    gate.append(f"- QC window status: PASS={n_pass}, REVIEW={n_review}, FAIL={n_fail} (n={n_qc})")
    gate.append(f"- PASS rate in QC window: {pass_rate:.1f}%")
    gate.append(
        f"- Context vs full explored scope: QC window n={n_qc} out of total n={n_total_scope}; "
        f"outside window status = PASS {outside_counts.get('PASS', 0)}, "
        f"REVIEW {outside_counts.get('REVIEW', 0)}, FAIL {outside_counts.get('FAIL', 0)}"
    )
    gate.append("")

    fit = []
    fit.append("## Fit Sanity (QC Window)")
    fit.append("")
    if pd.notna(mean_r2):
        fit.append(f"- Mean R2: {float(mean_r2):.4f}")
    if pd.notna(mean_mape):
        fit.append(f"- Mean MAPE: {float(mean_mape):.4f}")
    if pd.notna(mean_wmape):
        fit.append(f"- Mean wMAPE: {float(mean_wmape):.4f}")
    if pd.notna(max_baseline_neg_prob):
        fit.append(f"- Max baseline negative probability: {float(max_baseline_neg_prob):.4f}")
    fit.append("")

    outputs = []
    outputs.append("## Artifacts")
    outputs.append("")
    outputs.append(f"- Run subset table: `{table_run_rel}`")
    if table_rank_rel:
        outputs.append(f"- Channel sensitivity table: `{table_rank_rel}`")
    outputs.append("")

    rank_lines = []
    rank_lines.append("## Sensitivity Snapshot")
    rank_lines.append("")
    if rank_df.empty or not rank_metric:
        rank_lines.append("- Tornado input unavailable for this subset.")
    else:
        rank_lines.append(f"- Ranking metric: `{rank_metric}`")
        top = rank_df.head(5)
        for row in top.itertuples(index=False):
            rank_lines.append(
                f"- {row.channel}: max={float(row.max_change):.4f}, "
                f"median={float(row.median_change):.4f}, n={int(row.n)}"
            )
    rank_lines.append("")

    next_steps = []
    next_steps.append("## Recommended Next Step")
    next_steps.append("")
    if gate_pass:
        next_steps.append(
            "- Use this QC-passing 4-run window as the default gate for final capstone deliverables."
        )
        next_steps.append(
            "- Keep high-mu + LogNormal scenarios in appendix as stress tests (not decision defaults)."
        )
    else:
        next_steps.append(
            "- Investigate remaining REVIEW/FAIL rows before promoting this window to default."
        )
    next_steps.append("")

    out_md.write_text(
        "\n".join(header + gate + fit + outputs + rank_lines + next_steps),
        encoding="utf-8",
    )


def main() -> None:
    args = _build_parser().parse_args()
    targets_sorted, tag, targets_csv = _format_targets(args.targets)

    run_csv = _find_run_csv(tag)
    tornado_csv = _find_tornado_csv(tag)
    run_df = pd.read_csv(run_csv)

    qc_subset, scope_df = _build_qc_subset(
        run_df=run_df,
        targets_csv=targets_csv,
        mu_values=args.mu_values,
        sigma_values=args.sigma_values,
        dists=args.dists,
    )

    run_ids = set(qc_subset["run_id"].astype(str).tolist())
    rank_df, rank_metric = _build_channel_rank(tornado_csv=tornado_csv, run_ids=run_ids)

    outdir = Path(args.outdir) if args.outdir else (PROJECT_ROOT / "data" / "output" / "03_reports" / "report" / tag)
    tables_dir = outdir / "tables"
    outdir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    run_subset_cols = [
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
        if c in qc_subset.columns
    ]
    run_subset_out = tables_dir / "qc_gate_run_subset.csv"
    qc_subset[run_subset_cols].sort_values(
        ["roi_prior_mu", "roi_prior_sigma", "roi_prior_dist"],
        ascending=[True, True, True],
    ).to_csv(run_subset_out, index=False)

    rank_out = None
    if not rank_df.empty:
        rank_out = tables_dir / "qc_gate_channel_sensitivity.csv"
        rank_df.to_csv(rank_out, index=False)

    out_md = outdir / "qc_gate_summary.md"
    _write_markdown(
        out_md=out_md,
        targets_sorted=targets_sorted,
        run_csv=run_csv,
        tornado_csv=tornado_csv,
        qc_subset=qc_subset,
        scope_df=scope_df,
        rank_df=rank_df,
        rank_metric=rank_metric,
        table_run_rel=str(run_subset_out.relative_to(outdir)).replace("\\", "/"),
        table_rank_rel=(
            str(rank_out.relative_to(outdir)).replace("\\", "/")
            if rank_out is not None
            else None
        ),
    )

    print(f"QC gate summary written to: {out_md}")
    print(f"QC run subset table: {run_subset_out}")
    if rank_out is not None:
        print(f"QC channel sensitivity table: {rank_out}")


if __name__ == "__main__":
    main()
