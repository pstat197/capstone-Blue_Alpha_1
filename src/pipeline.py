from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.output_paths import (
    RUNS_DIR,
    candidate_roi_csv_paths,
    candidate_run_csv_paths,
    candidate_tornado_csv_paths,
    ensure_output_dirs,
    first_existing,
    report_input_csv_path,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="End-to-end pipeline: run sensitivity, summarize tornado CSV, plot tornado, build report.",
    )
    parser.add_argument("targets", nargs="+", help="Target channels to perturb together.")
    parser.add_argument(
        "--config",
        default="config/sensitivity.yaml",
        help="Run config YAML passed to src.main.",
    )
    parser.add_argument(
        "--dollars-per-subscription",
        type=float,
        default=100.0,
        help="Dollar value used by src.summarize_sensitivity.",
    )
    parser.add_argument(
        "--report-config",
        default="config/report_config.yaml",
        help="Config YAML for src.reporting.make_report.",
    )
    parser.add_argument(
        "--report-outdir",
        default="data/output/03_reports/report",
        help="Base output directory for HTML report; target tag subfolder is appended automatically.",
    )
    parser.add_argument(
        "--report-channel-scope",
        choices=["all"],
        default="all",
        help="Channel scope in report (currently fixed to all modeled channels).",
    )
    parser.add_argument(
        "--report-scenario-selection",
        choices=["largest_total_abs_pct_non_fail", "largest_total_abs_pct", "first_non_baseline"],
        default=None,
        help="Override auto-selection rule for single-scenario snapshot in report.",
    )
    parser.add_argument(
        "--tornado-outdir",
        default="data/output/03_reports/tornado_outputs",
        help="Base output directory for tornado PNG/HTML outputs; target tag subfolder is appended automatically.",
    )
    parser.add_argument(
        "--tornado-range-mode",
        choices=["minmax", "p05p95"],
        default="p05p95",
        help="Range mode for tornado bars.",
    )
    parser.add_argument(
        "--tornado-top-n",
        type=int,
        default=20,
        help="Max channels shown in tornado plot.",
    )
    parser.add_argument(
        "--skip-main",
        action="store_true",
        help="Skip src.main and reuse existing run/ROI outputs.",
    )
    parser.add_argument(
        "--skip-summarize",
        action="store_true",
        help="Skip src.summarize_sensitivity and reuse existing tornado CSV.",
    )
    parser.add_argument(
        "--skip-tornado",
        action="store_true",
        help="Skip src.viz.tornado_plots.",
    )
    parser.add_argument(
        "--skip-report",
        action="store_true",
        help="Skip src.reporting.make_report.",
    )
    return parser


def _run_step(cmd: list[str], project_root: Path) -> None:
    print("\n[run]", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=project_root)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {proc.returncode}: {' '.join(cmd)}")


def _to_project_rel_or_abs(path_str: str, project_root: Path) -> str:
    p = Path(path_str)
    try:
        return str(p.resolve().relative_to(project_root.resolve()))
    except Exception:
        return str(p)


def _build_report_input_csv(tag: str) -> tuple[Path, dict]:
    run_candidates = candidate_run_csv_paths(tag)
    roi_candidates = candidate_roi_csv_paths(tag)

    run_csv = None
    roi_csv = None
    if run_candidates[0].exists() and roi_candidates[0].exists():
        run_csv = run_candidates[0]
        roi_csv = roi_candidates[0]
    elif run_candidates[1].exists() and roi_candidates[1].exists():
        run_csv = run_candidates[1]
        roi_csv = roi_candidates[1]
    else:
        run_csv = first_existing(run_candidates)
        roi_csv = first_existing(roi_candidates)

    if run_csv is None:
        candidates = ", ".join(str(p) for p in run_candidates)
        raise FileNotFoundError(f"Missing run CSV for report. Tried: {candidates}")
    if roi_csv is None:
        candidates = ", ".join(str(p) for p in roi_candidates)
        raise FileNotFoundError(f"Missing ROI CSV for report. Tried: {candidates}")

    out_csv = report_input_csv_path(tag)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    run_df = pd.read_csv(run_csv)
    roi_df = pd.read_csv(roi_csv)
    tornado_candidates = candidate_tornado_csv_paths(tag)
    tornado_csv = first_existing(tornado_candidates)

    if "run_id" not in run_df.columns or "run_id" not in roi_df.columns:
        raise ValueError("Both run and ROI CSVs must include 'run_id'.")
    if "target_channel" not in run_df.columns and "targets" in run_df.columns:
        run_df["target_channel"] = run_df["targets"]

    run_base_cols = [
        "run_id",
        "target_channel",
        "roi_prior_mu",
        "roi_prior_sigma",
        "roi_prior_dist",
    ]
    missing_run = [c for c in run_base_cols if c not in run_df.columns]
    if missing_run:
        raise ValueError(f"Run CSV missing required report columns: {missing_run}")
    run_extra_cols = [c for c in ["prior_key", "targets", "is_baseline"] if c in run_df.columns]
    run_extra_cols.extend([c for c in run_df.columns if c.startswith("qc_")])
    run_cols = run_base_cols + run_extra_cols

    for col in ["channel", "estimated_roi"]:
        if col not in roi_df.columns:
            raise ValueError(f"ROI CSV missing required report column: {col}")

    run_meta = run_df[run_cols].drop_duplicates(subset=["run_id"]).copy()
    merged = roi_df.merge(run_meta, on="run_id", how="left")

    # Optionally enrich report input with tornado dollar/outcome deltas.
    if tornado_csv is not None:
        tornado_df = pd.read_csv(tornado_csv)
        if {"run_id", "channel"}.issubset(tornado_df.columns):
            tcols = [
                "run_id",
                "channel",
                "roi_baseline",
                "roi_new",
                "delta_abs",
                "delta_pct",
                "channel_total_spend",
                "incremental_outcome_baseline",
                "incremental_outcome_new",
                "delta_outcome",
                "delta_outcome_abs",
                "dollars_per_subscription",
                "incremental_value_baseline",
                "incremental_value_new",
                "delta_value",
                "delta_value_abs",
            ]
            tcols = [c for c in tcols if c in tornado_df.columns]
            if tcols:
                tmeta = tornado_df[tcols].drop_duplicates(subset=["run_id", "channel"]).copy()
                merged = merged.merge(tmeta, on=["run_id", "channel"], how="left")

    keep_cols = [
        "run_id",
        "channel",
        "target_channel",
        "roi_prior_mu",
        "roi_prior_sigma",
        "roi_prior_dist",
        "estimated_roi",
    ]
    keep_cols.extend([c for c in run_extra_cols if c in merged.columns])
    keep_cols.extend(
        [
            c
            for c in [
                "roi_baseline",
                "roi_new",
                "delta_abs",
                "delta_pct",
                "channel_total_spend",
                "incremental_outcome_baseline",
                "incremental_outcome_new",
                "delta_outcome",
                "delta_outcome_abs",
                "dollars_per_subscription",
                "incremental_value_baseline",
                "incremental_value_new",
                "delta_value",
                "delta_value_abs",
            ]
            if c in merged.columns
        ]
    )
    merged = merged[[c for c in keep_cols if c in merged.columns]].copy()
    merged.to_csv(out_csv, index=False)
    source_files = {
        "report_input": str(out_csv),
        "runs_csv": str(run_csv),
        "roi_csv": str(roi_csv),
        "tornado_csv": str(tornado_csv) if tornado_csv is not None else None,
    }
    return out_csv, source_files


def main() -> None:
    args = _build_parser().parse_args()

    ensure_output_dirs()
    project_root = Path(__file__).resolve().parents[1]
    targets = sorted({str(t) for t in args.targets})
    if not targets:
        raise ValueError("At least one target is required.")
    tag = "_".join(targets)

    tornado_candidates = candidate_tornado_csv_paths(tag)
    if args.skip_summarize:
        tornado_csv = first_existing(tornado_candidates) or tornado_candidates[0]
    else:
        tornado_csv = tornado_candidates[0]
    report_outdir = Path(args.report_outdir) / tag
    tornado_outdir = Path(args.tornado_outdir) / tag

    if not args.skip_main:
        cmd = [sys.executable, "-m", "src.main", "--targets", *targets]
        if args.config:
            cmd.extend(["--config", args.config])
        _run_step(cmd, project_root)

    if not args.skip_summarize:
        cmd = [
            sys.executable,
            "-m",
            "src.summarize_sensitivity",
            *targets,
            "--dollars_per_subscription",
            str(float(args.dollars_per_subscription)),
        ]
        _run_step(cmd, project_root)

    if not args.skip_tornado:
        tornado_outdir.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            "-m",
            "src.viz.tornado_plots",
            "--input-mode",
            "single",
            "--csv",
            str(tornado_csv.relative_to(project_root)),
            "--outdir",
            str(tornado_outdir),
            "--range-mode",
            args.tornado_range_mode,
            "--top-n",
            str(int(args.tornado_top_n)),
        ]
        _run_step(cmd, project_root)

    report_input_path = None
    report_source_files: dict | None = None
    if not args.skip_report:
        report_input_path, report_source_files = _build_report_input_csv(tag)
        cmd = [
            sys.executable,
            "-m",
            "src.reporting.make_report",
            "--input",
            str(report_input_path.relative_to(project_root)),
            "--outdir",
            str(report_outdir),
            "--config",
            args.report_config,
            "--clean-output",
        ]
        if report_source_files is not None:
            if report_source_files.get("runs_csv"):
                cmd.extend(["--source-runs-csv", _to_project_rel_or_abs(report_source_files["runs_csv"], project_root)])
            if report_source_files.get("roi_csv"):
                cmd.extend(["--source-roi-csv", _to_project_rel_or_abs(report_source_files["roi_csv"], project_root)])
            if report_source_files.get("tornado_csv"):
                cmd.extend(["--source-tornado-csv", _to_project_rel_or_abs(report_source_files["tornado_csv"], project_root)])
        cmd.extend(["--channel-scope", args.report_channel_scope])
        if args.report_scenario_selection:
            cmd.extend(["--scenario-selection", args.report_scenario_selection])
        _run_step(cmd, project_root)

    print("\nPipeline finished.")
    print("Targets:", ", ".join(targets))
    print("Run outputs dir:", RUNS_DIR)
    print("Tornado CSV:", tornado_csv)
    print("Tornado outputs:", tornado_outdir)
    if report_input_path is not None:
        print("Report input table:", report_input_path)
    print("Report output:", project_root / report_outdir)


if __name__ == "__main__":
    main()
