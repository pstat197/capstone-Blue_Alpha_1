import argparse
import os
from typing import Any

import pandas as pd

from src.run_config import load_run_config, dump_run_config
from src.output_paths import candidate_run_csv_paths, first_existing


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("targets", nargs="+")
    parser.add_argument("-c", "--config-in", default="config/sensitivity.yaml")
    parser.add_argument("-o", "--config-out", default=None)
    return parser


def _tag_for_targets(targets: list[str]) -> str:
    return "_".join(sorted(str(t) for t in targets))


def _run_csv_path(project_root: str, tag: str) -> str:
    del project_root  # kept for backward signature compatibility
    chosen = first_existing(candidate_run_csv_paths(tag))
    if chosen is None:
        return str(candidate_run_csv_paths(tag)[0])
    return str(chosen)


def _pass_rate(s: pd.Series) -> float:
    if len(s) == 0:
        return 0.0
    return float((s.astype(str) == "PASS").mean())


def _baseline_issue_rate(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return float(
        (
            df.get("qc_primary_review_check", pd.Series(dtype=object))
            .astype(str)
            .eq("Baseline")
            .mean()
        )
    )


def _recommended_dists(run_df: pd.DataFrame, policy: dict[str, Any]) -> list[str]:
    min_dist_pass_rate = float(policy.get("min_dist_pass_rate", 0.7))
    max_baseline_issue_rate = float(policy.get("max_baseline_issue_rate", 0.1))
    fallback_keep_all_dists = bool(policy.get("fallback_keep_all_dists", True))

    dists = []
    for dist, group in run_df.groupby("roi_prior_dist", dropna=False):
        pass_rate = _pass_rate(group["qc_status_code"])
        baseline_issue_rate = _baseline_issue_rate(group)
        if pass_rate >= min_dist_pass_rate and baseline_issue_rate <= max_baseline_issue_rate:
            dists.append(str(dist))

    if not dists and fallback_keep_all_dists:
        dists = sorted(run_df["roi_prior_dist"].dropna().astype(str).unique().tolist())
    return dists


def _recommended_numeric_values(
    run_df: pd.DataFrame,
    col: str,
    min_param_pass_rate: float,
) -> list[float]:
    out = []
    for val, group in run_df.groupby(col, dropna=False):
        try:
            numeric_val = float(val)
        except Exception:
            continue
        pass_rate = _pass_rate(group["qc_status_code"])
        if pass_rate >= min_param_pass_rate:
            out.append(round(numeric_val, 6))

    if not out:
        out = sorted(pd.to_numeric(run_df[col], errors="coerce").dropna().round(6).unique().tolist())
    return sorted(out)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    targets = sorted(str(t) for t in args.targets)
    tag = _tag_for_targets(targets)

    config_in = args.config_in
    if not os.path.isabs(config_in):
        config_in = os.path.join(project_root, config_in)
    config_out = args.config_out or os.path.join(project_root, "config", f"sensitivity_{tag}_next.yaml")
    if not os.path.isabs(config_out):
        config_out = os.path.join(project_root, config_out)

    run_cfg = load_run_config(config_in)
    run_csv = _run_csv_path(project_root, tag)
    if not os.path.exists(run_csv):
        raise FileNotFoundError(f"Run CSV not found for targets={tag}: {run_csv}")

    run_df = pd.read_csv(run_csv)
    if run_df.empty:
        raise ValueError(f"Run CSV is empty: {run_csv}")

    policy = run_cfg.get("next_grid_policy", {})
    min_param_pass_rate = float(policy.get("min_param_pass_rate", 0.6))

    dists = _recommended_dists(run_df, policy)
    filtered = run_df[run_df["roi_prior_dist"].astype(str).isin(dists)].copy() if dists else run_df.copy()

    mu_values = _recommended_numeric_values(filtered, "roi_prior_mu", min_param_pass_rate)
    sigma_values = _recommended_numeric_values(filtered, "roi_prior_sigma", min_param_pass_rate)

    run_cfg.setdefault("defaults", {})
    run_cfg["defaults"]["targets"] = targets

    run_cfg.setdefault("experiment", {})
    run_cfg["experiment"]["roi_mu_values"] = mu_values
    run_cfg["experiment"]["roi_sigma_values"] = sigma_values
    run_cfg["experiment"]["roi_dist_values"] = dists

    run_cfg.setdefault("meta", {})
    run_cfg["meta"]["generated_from"] = os.path.relpath(
        run_csv, os.path.join(project_root, "data", "output")
    ).replace("\\", "/")
    run_cfg["meta"]["recommended_target"] = tag

    dump_run_config(run_cfg, config_out)

    print(f"Target set: {tag}")
    print(f"Input run CSV: {run_csv}")
    print(f"Recommended dists: {dists}")
    print(f"Recommended mu grid: {mu_values}")
    print(f"Recommended sigma grid: {sigma_values}")
    print(f"Wrote config: {config_out}")


if __name__ == "__main__":
    main()
