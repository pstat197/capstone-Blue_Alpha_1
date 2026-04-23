from __future__ import annotations

import argparse
import copy
import shutil
import subprocess
import sys
from typing import Any
from pathlib import Path

import pandas as pd

from src.io_utils import STRUCTURAL_COLUMNS
from src.output_paths import (
    OUTPUT_ROOT,
    RUNS_DIR,
    ensure_output_dirs,
    report_input_csv_path,
    roi_csv_path,
    run_csv_path,
    tornado_csv_path,
)
from src.run_config import dump_run_config, load_run_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="End-to-end pipeline: run sensitivity, summarize tornado CSV, plot tornado, compute robustness score, build dashboard.",
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


def _cleanup_tag_outputs(tag: str, project_root: Path, dashboard_outdir_base: Path, tornado_outdir_base: Path) -> None:
    tag_paths = [
        RUNS_DIR / tag,
        Path("data/output/02_tables") / tag,
        dashboard_outdir_base / tag,
        tornado_outdir_base / tag,
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

    # Remove temporary two-layer config files for this tag.
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


def _coerce_numeric_list(raw: Any) -> list[float]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set, pd.Series, pd.Index)):
        items = list(raw)
    else:
        items = [raw]
    out: list[float] = []
    seen: set[float] = set()
    for v in items:
        val = round(float(v), 6)
        if val in seen:
            continue
        seen.add(val)
        out.append(val)
    return out


def _coerce_string_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set, pd.Series, pd.Index)):
        items = list(raw)
    else:
        items = [raw]
    out: list[str] = []
    seen: set[str] = set()
    for v in items:
        s = str(v).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _resolve_layer_grid(layer_cfg: dict[str, Any] | None, base_grid: dict[str, Any], label: str) -> dict[str, list[Any]]:
    cfg = layer_cfg if isinstance(layer_cfg, dict) else {}
    mu = _coerce_numeric_list(cfg.get("roi_mu_values"))
    sigma = _coerce_numeric_list(cfg.get("roi_sigma_values"))
    dist = _coerce_string_list(cfg.get("roi_dist_values"))
    if not mu:
        mu = _coerce_numeric_list(base_grid.get("roi_mu_values"))
    if not sigma:
        sigma = _coerce_numeric_list(base_grid.get("roi_sigma_values"))
    if not dist:
        dist = _coerce_string_list(base_grid.get("roi_dist_values"))
    if not mu or not sigma or not dist:
        raise ValueError(f"{label} grid is incomplete. Require roi_mu_values, roi_sigma_values, roi_dist_values.")
    return {
        "roi_mu_values": mu,
        "roi_sigma_values": sigma,
        "roi_dist_values": dist,
    }


def _center(values: list[float]) -> float:
    vals = sorted(values)
    return vals[len(vals) // 2]


def _build_layer_config(base_cfg: dict[str, Any], grid: dict[str, list[Any]]) -> dict[str, Any]:
    cfg = copy.deepcopy(base_cfg)
    cfg.setdefault("experiment", {})
    cfg["experiment"]["roi_mu_values"] = [float(v) for v in grid["roi_mu_values"]]
    cfg["experiment"]["roi_sigma_values"] = [float(v) for v in grid["roi_sigma_values"]]
    cfg["experiment"]["roi_dist_values"] = [str(v) for v in grid["roi_dist_values"]]
    cfg.setdefault("baseline", {})
    cfg["baseline"]["roi_mu"] = _center(cfg["experiment"]["roi_mu_values"])
    cfg["baseline"]["roi_sigma"] = _center(cfg["experiment"]["roi_sigma_values"])
    cfg["baseline"]["roi_dist"] = str(cfg["experiment"]["roi_dist_values"][0])
    return cfg


def _write_layer_config(project_root: Path, tag: str, layer_name: str, run_cfg: dict[str, Any]) -> Path:
    tmp_dir = project_root / "data" / "output" / "_tmp_configs"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_path = tmp_dir / f"sensitivity_{tag}_{layer_name}.yaml"
    dump_run_config(run_cfg, str(out_path))
    return out_path


def _dense_between(lo: float, hi: float, step: float) -> list[float]:
    lo = round(float(lo), 6)
    hi = round(float(hi), 6)
    step = float(step)
    if step <= 0:
        raise ValueError("Step must be > 0 for dense grid generation.")
    if hi < lo:
        lo, hi = hi, lo
    out: list[float] = []
    v = lo
    guard = 0
    while v <= hi + 1e-9:
        out.append(round(v, 6))
        v += step
        guard += 1
        if guard > 10000:
            break
    if out and abs(out[-1] - hi) > 1e-6:
        out.append(round(hi, 6))
    return sorted(set(out))


def _best_local_points(all_values: list[float], best_value: float, top_n: int) -> list[float]:
    if not all_values:
        return []
    n = max(1, min(int(top_n), len(all_values)))
    picked = sorted(all_values, key=lambda v: (abs(float(v) - float(best_value)), float(v)))[:n]
    return sorted(set(round(float(x), 6) for x in picked))


def _derive_layer2_grid(
    *,
    layer1_run_csv: Path | None,
    targets: list[str],
    layer2_cfg: dict[str, Any] | None,
    fallback_grid: dict[str, list[Any]],
) -> dict[str, list[Any]]:
    cfg = layer2_cfg if isinstance(layer2_cfg, dict) else {}

    explicit_mu = _coerce_numeric_list(cfg.get("roi_mu_values"))
    explicit_sigma = _coerce_numeric_list(cfg.get("roi_sigma_values"))
    explicit_dist = _coerce_string_list(cfg.get("roi_dist_values"))
    if explicit_mu and explicit_sigma:
        return {
            "roi_mu_values": explicit_mu,
            "roi_sigma_values": explicit_sigma,
            "roi_dist_values": explicit_dist or list(fallback_grid["roi_dist_values"]),
        }

    fallback_cfg = cfg.get("fallback", {}) if isinstance(cfg.get("fallback"), dict) else {}
    fallback = _resolve_layer_grid(fallback_cfg, fallback_grid, "two_layer.layer2.fallback")
    if layer1_run_csv is None or not layer1_run_csv.exists():
        return fallback

    run_df = pd.read_csv(layer1_run_csv)
    targets_str = ",".join(sorted(str(x) for x in targets))
    if "targets" in run_df.columns:
        run_df = run_df[run_df["targets"].astype(str) == targets_str].copy()

    if run_df.empty or "roi_prior_mu" not in run_df.columns or "roi_prior_sigma" not in run_df.columns:
        return fallback

    run_df["roi_prior_mu"] = pd.to_numeric(run_df["roi_prior_mu"], errors="coerce")
    run_df["roi_prior_sigma"] = pd.to_numeric(run_df["roi_prior_sigma"], errors="coerce")
    run_df = run_df.dropna(subset=["roi_prior_mu", "roi_prior_sigma"]).copy()
    if run_df.empty:
        return fallback

    run_df["qc_status_code"] = run_df.get("qc_status_code", "REVIEW").astype(str).str.upper()
    run_df["qc_baseline_status"] = run_df.get("qc_baseline_status", "REVIEW").astype(str).str.upper()

    status_score = {"PASS": 2.0, "REVIEW": 1.0, "FAIL": 0.0}
    baseline_score = {"PASS": 1.0, "REVIEW": 0.5, "FAIL": -1.0}
    run_df["row_score"] = run_df["qc_status_code"].map(status_score).fillna(0.0) + run_df["qc_baseline_status"].map(
        baseline_score
    ).fillna(0.0)

    non_fail = run_df["qc_status_code"] != "FAIL"
    baseline_non_fail = run_df["qc_baseline_status"] != "FAIL"
    candidate = run_df[non_fail & baseline_non_fail].copy()
    if candidate.empty:
        candidate = run_df[non_fail].copy()
    if candidate.empty:
        candidate = run_df.copy()

    mu_scores = candidate.groupby("roi_prior_mu")["row_score"].mean()
    sigma_scores = candidate.groupby("roi_prior_sigma")["row_score"].mean()
    if mu_scores.empty or sigma_scores.empty:
        return fallback

    best_mu = float(mu_scores.sort_values(ascending=False).index[0])
    best_sigma = float(sigma_scores.sort_values(ascending=False).index[0])
    all_mu = sorted(float(x) for x in run_df["roi_prior_mu"].dropna().unique().tolist())
    all_sigma = sorted(float(x) for x in run_df["roi_prior_sigma"].dropna().unique().tolist())
    top_n_mu = int(cfg.get("top_n_mu", 3))
    top_n_sigma = int(cfg.get("top_n_sigma", 2))
    picked_mu = _best_local_points(all_mu, best_mu, top_n_mu)
    picked_sigma = _best_local_points(all_sigma, best_sigma, top_n_sigma)
    if not picked_mu or not picked_sigma:
        return fallback

    mu_step = float(cfg.get("mu_step", 0.25))
    sigma_step = float(cfg.get("sigma_step", 0.25))
    refined_mu = _dense_between(min(picked_mu), max(picked_mu), mu_step)
    refined_sigma = _dense_between(min(picked_sigma), max(picked_sigma), sigma_step)
    if not refined_mu or not refined_sigma:
        return fallback

    dist_values = _coerce_string_list(cfg.get("roi_dist_values"))
    if not dist_values:
        dist_values = _coerce_string_list(candidate.get("roi_prior_dist"))
    if not dist_values:
        dist_values = list(fallback["roi_dist_values"])

    return {
        "roi_mu_values": refined_mu,
        "roi_sigma_values": refined_sigma,
        "roi_dist_values": dist_values,
    }


def _fmt_grid(values: list[Any]) -> str:
    return "[" + ", ".join(str(v) for v in values) + "]"


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
    tornado_csv = tornado_csv_path(tag)

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
        raise ValueError(f"Run CSV missing required dashboard columns: {missing_run}")
    run_extra_cols = [
        c
        for c in [
            "prior_key",
            "targets",
            "is_baseline",
            *STRUCTURAL_COLUMNS,
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
    two_layer_cfg = run_cfg.get("two_layer", {}) if isinstance(run_cfg.get("two_layer"), dict) else {}
    two_layer_enabled = bool(two_layer_cfg.get("enabled", False))
    if not two_layer_enabled:
        raise ValueError("two_layer.enabled must be true. Old one-layer mode has been removed.")
    clean_between_layers = bool(two_layer_cfg.get("clean_between_layers", True))

    dashboard_outdir_base_abs = Path(args.dashboard_outdir)
    if not dashboard_outdir_base_abs.is_absolute():
        dashboard_outdir_base_abs = (project_root / dashboard_outdir_base_abs).resolve()
    tornado_outdir_base_abs = Path(args.tornado_outdir)
    if not tornado_outdir_base_abs.is_absolute():
        tornado_outdir_base_abs = (project_root / tornado_outdir_base_abs).resolve()

    built_tags: list[str] = []
    for targets in target_sets:
        tag = "_".join(targets)
        built_tags.append(tag)
        print(f"\n=== Target set: {', '.join(targets)} (tag: {tag}) ===")

        tornado_csv = tornado_csv_path(tag)
        dashboard_outdir = Path(args.dashboard_outdir) / tag
        tornado_outdir = Path(args.tornado_outdir) / tag

        if not args.skip_main:
            layer1_grid = _resolve_layer_grid(
                two_layer_cfg.get("layer1"),
                run_cfg.get("experiment", {}),
                "two_layer.layer1",
            )
            layer1_cfg = _build_layer_config(run_cfg, layer1_grid)
            layer1_cfg_path = _write_layer_config(project_root, tag, "layer1", layer1_cfg)

            print(f"[clean] Removing existing outputs for tag={tag} before Layer 1.")
            _cleanup_tag_outputs(tag, project_root, dashboard_outdir_base_abs, tornado_outdir_base_abs)

            print(
                "[layer1] grid:",
                f"mu={_fmt_grid(layer1_grid['roi_mu_values'])}; "
                f"sigma={_fmt_grid(layer1_grid['roi_sigma_values'])}; "
                f"dist={_fmt_grid(layer1_grid['roi_dist_values'])}",
            )
            cmd = [sys.executable, "-m", "src.main", "--targets", *targets, "--config", str(layer1_cfg_path)]
            _run_step(cmd, project_root)

            layer1_run_csv = run_csv_path(tag)
            layer2_grid = _derive_layer2_grid(
                layer1_run_csv=layer1_run_csv,
                targets=targets,
                layer2_cfg=two_layer_cfg.get("layer2"),
                fallback_grid=layer1_grid,
            )
            print(
                "[layer2] grid:",
                f"mu={_fmt_grid(layer2_grid['roi_mu_values'])}; "
                f"sigma={_fmt_grid(layer2_grid['roi_sigma_values'])}; "
                f"dist={_fmt_grid(layer2_grid['roi_dist_values'])}",
            )

            if clean_between_layers:
                print(f"[clean] Removing Layer 1 outputs for tag={tag} before Layer 2.")
                _cleanup_tag_outputs(tag, project_root, dashboard_outdir_base_abs, tornado_outdir_base_abs)

            layer2_cfg = _build_layer_config(run_cfg, layer2_grid)
            layer2_cfg_path = _write_layer_config(project_root, tag, "layer2", layer2_cfg)
            cmd = [sys.executable, "-m", "src.main", "--targets", *targets, "--config", str(layer2_cfg_path)]
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

        if not args.skip_robustness:
            robustness_outdir = Path("data/output/02_tables") / tag
            cmd = [
                sys.executable,
                "-m",
                "src.robustness_score",
                *targets,
                "--out-dir",
                str(robustness_outdir),
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

        print("Finished target set:", ", ".join(targets))
        print("Run outputs dir:", RUNS_DIR)
        print("Tornado CSV:", tornado_csv)
        print("Tornado outputs:", tornado_outdir)
        if dashboard_input_path is not None:
            print("Dashboard input table:", dashboard_input_path)
        print("Dashboard output:", project_root / dashboard_outdir)

    print("\nPipeline finished for tags:", ", ".join(built_tags))


if __name__ == "__main__":
    main()
