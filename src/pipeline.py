from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from typing import Any
from pathlib import Path

import pandas as pd

from src.baseline_utils import require_explicit_baseline_rows
from src.io_utils import EXPERIMENT_METADATA_COLUMNS, STRUCTURAL_COLUMNS
from src.output_paths import (
    OUTPUT_ROOT,
    RUNS_DIR,
    ensure_output_dirs,
    report_input_csv_path,
    roi_csv_path,
    run_csv_path,
    tornado_csv_path,
)
from src.run_config import load_run_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="End-to-end pipeline: run sensitivity, summarize tornado CSV, compute robustness score, build dashboard payload.",
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help="Optional target channels to perturb together. If omitted, pipeline uses defaults.targets or defaults.target_sets from YAML.",
    )
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
        "--dashboard-config",
        "--report-config",
        dest="dashboard_config",
        default="config/dashboard.yaml",
        help="Config YAML for src.reporting.make_dashboard.",
    )
    parser.add_argument(
        "--dashboard-outdir",
        "--report-outdir",
        dest="dashboard_outdir",
        default="data/output/03_reports/report",
        help="Base output directory for dashboard HTML; target tag subfolder is appended automatically.",
    )
    parser.add_argument(
        "--dashboard-channel-scope",
        "--report-channel-scope",
        dest="dashboard_channel_scope",
        choices=["all"],
        default="all",
        help="Channel scope in dashboard (currently fixed to all modeled channels).",
    )
    parser.add_argument(
        "--dashboard-scenario-selection",
        "--report-scenario-selection",
        dest="dashboard_scenario_selection",
        choices=["largest_total_abs_pct_non_fail", "largest_total_abs_pct", "first_non_baseline"],
        default=None,
        help="Override auto-selection rule for single-scenario snapshot in dashboard.",
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
        "--skip-robustness",
        action="store_true",
        help="Skip src.robustness_score.",
    )
    parser.add_argument(
        "--skip-dashboard",
        "--skip-report",
        dest="skip_dashboard",
        action="store_true",
        help="Skip src.reporting.make_dashboard.",
    )
    return parser


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted({str(v).strip() for v in values if str(v).strip()})


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


def _tag_for_target_set(targets: list[str], run_cfg: dict) -> str:
    output_cfg = run_cfg.get("output", {}) or {}
    explicit_tag = output_cfg.get("tag")
    if explicit_tag is None or str(explicit_tag).strip().lower() in {"", "null", "none"}:
        return "_".join(targets)
    return _sanitize_tag_token(str(explicit_tag))


def _resolve_target_sets(args: argparse.Namespace, run_cfg: dict) -> list[list[str]]:
    if args.targets:
        targets = _unique_sorted(list(args.targets))
        if not targets:
            raise ValueError("At least one target is required when passing CLI targets.")
        return [targets]

    defaults = run_cfg.get("defaults", {}) or {}
    raw_sets = defaults.get("target_sets")
    if raw_sets:
        out_sets = []
        for idx, raw in enumerate(raw_sets):
            if not isinstance(raw, list):
                raise ValueError(f"defaults.target_sets[{idx}] must be a list of channel names.")
            target_set = _unique_sorted(raw)
            if not target_set:
                raise ValueError(f"defaults.target_sets[{idx}] cannot be empty.")
            out_sets.append(target_set)
        if out_sets:
            return out_sets

    default_targets = _unique_sorted(defaults.get("targets", []))
    if not default_targets:
        raise ValueError("No targets found. Set defaults.targets (or defaults.target_sets) in config YAML, or pass CLI targets.")
    return [default_targets]


def _run_step(cmd: list[str], project_root: Path) -> None:
    step_name = cmd[0]
    if "-m" in cmd:
        mod_idx = cmd.index("-m")
        if mod_idx + 1 < len(cmd):
            step_name = cmd[mod_idx + 1]
    else:
        step_name = Path(cmd[0]).name
    print(f"\n[run] {step_name}")
    proc = subprocess.run(cmd, cwd=project_root)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {proc.returncode}: {' '.join(cmd)}")


def _to_project_rel_or_abs(path_str: str, project_root: Path) -> str:
    p = Path(path_str)
    try:
        return str(p.resolve().relative_to(project_root.resolve()))
    except Exception:
        return str(p)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _safe_remove(path: Path, *, allowed_root: Path) -> bool:
    if not path.exists():
        return True
    if not _is_within(path, allowed_root):
        print(f"[warn] Skip cleanup outside output root: {path}")
        return False
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True
    except PermissionError:
        return False


def _cleanup_tag_outputs(
    tag: str,
    project_root: Path,
    dashboard_outdir_base: Path,
) -> None:
    tag_paths = [
        RUNS_DIR / tag,
        Path("data/output/02_tables") / tag,
        dashboard_outdir_base / tag,
        Path("data/output/03_reports/tornado_outputs") / tag,
        report_input_csv_path(tag),
        run_csv_path(tag),
        roi_csv_path(tag),
        tornado_csv_path(tag),
    ]

    locked_paths: list[str] = []
    for raw in tag_paths:
        p = raw if raw.is_absolute() else (project_root / raw)
        ok = _safe_remove(p, allowed_root=OUTPUT_ROOT)
        if not ok and p.exists():
            locked_paths.append(str(p))

    # Remove temporary config files for this tag.
    tmp_cfg_dir = project_root / "data" / "output" / "_tmp_configs"
    if tmp_cfg_dir.exists():
        for p in tmp_cfg_dir.glob(f"sensitivity_{tag}_*.yaml"):
            ok = _safe_remove(p, allowed_root=OUTPUT_ROOT)
            if not ok and p.exists():
                locked_paths.append(str(p))

    if locked_paths:
        preview = "\n".join(locked_paths[:8])
        more = "" if len(locked_paths) <= 8 else f"\n... and {len(locked_paths) - 8} more"
        raise PermissionError(
            "Cannot clean old outputs because some files are locked.\n"
            "Close browser tabs / Excel / file previews using output files, then rerun.\n"
            f"Locked paths:\n{preview}{more}"
        )


def _build_dashboard_input_csv(tag: str) -> tuple[Path, dict]:
    run_csv = run_csv_path(tag)
    roi_csv = roi_csv_path(tag)
    if not run_csv.exists():
        raise FileNotFoundError(f"Missing run CSV for dashboard: {run_csv}")
    if not roi_csv.exists():
        raise FileNotFoundError(f"Missing ROI CSV for dashboard: {roi_csv}")

    out_csv = report_input_csv_path(tag)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    run_df = pd.read_csv(run_csv)
    roi_df = pd.read_csv(roi_csv)
    if "target_channel" not in run_df.columns and "targets" in run_df.columns:
        run_df["target_channel"] = run_df["targets"]
    require_explicit_baseline_rows(run_df, context=f"Run CSV {run_csv}")
    tornado_csv = tornado_csv_path(tag)

    if "run_id" not in run_df.columns or "run_id" not in roi_df.columns:
        raise ValueError("Both run and ROI CSVs must include 'run_id'.")

    run_base_cols = [
        "run_id",
        "target_channel",
        "roi_prior_mu",
        "roi_prior_sigma",
        "roi_prior_dist",
    ]
    missing_run = [c for c in run_base_cols if c not in run_df.columns]
    if missing_run:
        raise ValueError(f"Run CSV missing required dashboard columns: {missing_run}")
    run_extra_cols = [
        c
        for c in [
            "prior_key",
            "targets",
            "is_baseline",
            *STRUCTURAL_COLUMNS,
            *EXPERIMENT_METADATA_COLUMNS,
        ]
        if c in run_df.columns
    ]
    run_extra_cols.extend([c for c in run_df.columns if c.startswith("qc_")])
    run_extra_cols.extend([c for c in run_df.columns if c.startswith("data_")])
    run_cols = run_base_cols + run_extra_cols

    for col in ["channel", "estimated_roi"]:
        if col not in roi_df.columns:
            raise ValueError(f"ROI CSV missing required dashboard column: {col}")

    run_meta = run_df[run_cols].drop_duplicates(subset=["run_id"]).copy()

    # Avoid _x/_y collisions when ROI already carries base prior columns.
    # Keep run-side columns only if they are missing on ROI, plus run_id/qc diagnostics.
    run_merge_cols = ["run_id"]
    for col in run_meta.columns:
        if col == "run_id":
            continue
        if col.startswith("qc_") or (col not in roi_df.columns):
            run_merge_cols.append(col)
    run_meta = run_meta[run_merge_cols].copy()

    merged = roi_df.merge(run_meta, on="run_id", how="left")

    # Optionally enrich report input with tornado dollar/outcome deltas.
    if tornado_csv.exists():
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
        "is_target_channel",
        "roi_prior_mu",
        "roi_prior_sigma",
        "roi_prior_dist",
        "prior_roi_mu_channel",
        "prior_roi_sigma_channel",
        "prior_roi_dist_channel",
        "estimated_roi",
        "posterior_roi_sd",
        "posterior_roi_p05",
        "posterior_roi_p25",
        "posterior_roi_p50",
        "posterior_roi_p75",
        "posterior_roi_p95",
        "prior_posterior_kl_gaussian",
        "prior_posterior_wasserstein",
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
        "tornado_csv": str(tornado_csv) if tornado_csv.exists() else None,
    }
    return out_csv, source_files


def main() -> None:
    args = _build_parser().parse_args()

    ensure_output_dirs()
    project_root = Path(__file__).resolve().parents[1]
    config_path = args.config
    if config_path and not Path(config_path).is_absolute():
        config_path = str((project_root / config_path).resolve())
    run_cfg = load_run_config(config_path)
    target_sets = _resolve_target_sets(args, run_cfg)

    dashboard_outdir_base_abs = Path(args.dashboard_outdir)
    if not dashboard_outdir_base_abs.is_absolute():
        dashboard_outdir_base_abs = (project_root / dashboard_outdir_base_abs).resolve()

    built_tags: list[str] = []
    for targets in target_sets:
        tag = _tag_for_target_set(targets, run_cfg)
        built_tags.append(tag)
        print(f"\n=== Target set: {', '.join(targets)} ===")

        tornado_csv = tornado_csv_path(tag)
        dashboard_outdir = Path(args.dashboard_outdir) / tag

        if not args.skip_main:
            print(f"[clean] Removing existing outputs for tag={tag} before fixed full-grid run.")
            _cleanup_tag_outputs(tag, project_root, dashboard_outdir_base_abs)
            cmd = [sys.executable, "-m", "src.main", "--targets", *targets, "--config", str(config_path)]
            _run_step(cmd, project_root)

        if not args.skip_summarize:
            cmd = [
                sys.executable,
                "-m",
                "src.summarize_sensitivity",
                *targets,
                "--dollars_per_subscription",
                str(float(args.dollars_per_subscription)),
                "--tag",
                tag,
            ]
            _run_step(cmd, project_root)

        if not args.skip_robustness:
            robustness_outdir = Path("data/output/02_tables") / tag
            cmd = [
                sys.executable,
                "-m",
                "src.robustness_score",
                *targets,
                "--out-dir",
                str(robustness_outdir),
                "--tag",
                tag,
            ]
            _run_step(cmd, project_root)

        dashboard_input_path = None
        dashboard_source_files: dict | None = None
        if not args.skip_dashboard:
            dashboard_input_path, dashboard_source_files = _build_dashboard_input_csv(tag)
            cmd = [
                sys.executable,
                "-m",
                "src.reporting.make_dashboard",
                "--input",
                str(dashboard_input_path.relative_to(project_root)),
                "--outdir",
                str(dashboard_outdir),
                "--config",
                args.dashboard_config,
                "--clean-output",
            ]
            if dashboard_source_files is not None:
                if dashboard_source_files.get("runs_csv"):
                    cmd.extend(["--source-runs-csv", _to_project_rel_or_abs(dashboard_source_files["runs_csv"], project_root)])
                if dashboard_source_files.get("roi_csv"):
                    cmd.extend(["--source-roi-csv", _to_project_rel_or_abs(dashboard_source_files["roi_csv"], project_root)])
                if dashboard_source_files.get("tornado_csv"):
                    cmd.extend(["--source-tornado-csv", _to_project_rel_or_abs(dashboard_source_files["tornado_csv"], project_root)])
            cmd.extend(["--channel-scope", args.dashboard_channel_scope])
            if args.dashboard_scenario_selection:
                cmd.extend(["--scenario-selection", args.dashboard_scenario_selection])
            _run_step(cmd, project_root)

        print("Target set complete:", ", ".join(targets))

    print("\nPipeline complete:", ", ".join(built_tags))


if __name__ == "__main__":
    main()
