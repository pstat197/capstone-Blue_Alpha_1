from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd
import yaml

from src.baseline_utils import require_explicit_baseline_rows

try:
    from .metrics import compute_all_metrics
    from .render import render_dashboard_payload
except ImportError:  # Allow direct script execution.
    from metrics import compute_all_metrics
    from render import render_dashboard_payload


_REQUIRED_COLS = {
    "channel",
    "target_channel",
    "roi_prior_mu",
    "roi_prior_sigma",
    "roi_prior_dist",
    "estimated_roi",
}

_LEGACY_REPORT_FIGURE_PREFIXES = ("scenario_snapshot_", "heatmap_board_")
_LEGACY_REPORT_FIGURE_NAMES = {
    "tornado_top_sensitivity.png",
    "tornado_dollar_sensitivity.png",
    "roi_prior_vs_posterior.png",
    "spend_vs_effect_onepager.png",
    "structural_adstock_curves.png",
    "structural_saturation_curves.png",
    "structural_carryover_decomposition.png",
}


def _infer_output_tag_from_input(input_path: Path) -> str | None:
    stem = input_path.stem
    prefix = "prior_sensitivity_report_input_"
    if stem.startswith(prefix):
        return stem[len(prefix):]
    return input_path.parent.name or None


def _infer_roi_source_csv(input_path: Path) -> str | None:
    project_root = Path(__file__).resolve().parents[2]
    tag = _infer_output_tag_from_input(input_path)
    if not tag:
        return None
    candidate = project_root / "data" / "output" / "01_runs" / tag / f"prior_sensitivity_roi_multi_{tag}.csv"
    if not candidate.exists():
        return None
    try:
        return str(candidate.relative_to(project_root))
    except ValueError:
        return str(candidate)


def _empty_figure_paths() -> dict:
    return {
        "tornado": None,
        "tornado_dollar": None,
        "spend_effect": None,
        "adstock_curves": None,
        "saturation_curves": None,
        "carryover_decomposition": None,
        "scenario_snapshot": None,
        "scenario_snapshots": [],
        "heatmap_pages": [],
        "heatmap_modes": [],
        "default_heatmap_mode": None,
        "roi_prior_vs_posterior": None,
    }


def _cleanup_legacy_report_outputs(outdir: Path, report_filename: str) -> None:
    legacy_files = [outdir / report_filename, outdir / "dashboard.html", outdir / "dashboard.css"]
    for report_path in legacy_files:
        if not report_path.exists() or not report_path.is_file():
            continue
        try:
            report_path.unlink()
        except Exception:
            pass

    assets_dir = outdir / "assets"
    if assets_dir.exists() and assets_dir.is_dir():
        try:
            shutil.rmtree(assets_dir)
        except Exception:
            pass

    figures_dir = outdir / "figures"
    if not figures_dir.exists() or not figures_dir.is_dir():
        return
    for p in figures_dir.glob("*.png"):
        name = p.name
        if (
            name in _LEGACY_REPORT_FIGURE_NAMES
            or any(name.startswith(prefix) and name.endswith(".png") for prefix in _LEGACY_REPORT_FIGURE_PREFIXES)
        ):
            try:
                p.unlink()
            except Exception:
                continue
    meridian_official_dir = figures_dir / "meridian_official"
    if meridian_official_dir.exists() and meridian_official_dir.is_dir():
        try:
            shutil.rmtree(meridian_official_dir)
        except Exception:
            pass


def load_results(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    missing = _REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    require_explicit_baseline_rows(
        df,
        context=f"Dashboard input {csv_path}",
        require_columns=("is_baseline",),
    )
    df["roi_prior_mu"] = df["roi_prior_mu"].astype(float)
    df["roi_prior_sigma"] = df["roi_prior_sigma"].astype(float)
    df["estimated_roi"] = df["estimated_roi"].astype(float)
    df["channel"] = df["channel"].astype(str)
    df["target_channel"] = df["target_channel"].astype(str)
    df["roi_prior_dist"] = df["roi_prior_dist"].astype(str)
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="data/output/02_tables/all_channels/prior_sensitivity_results_all_channels.csv",
    )
    parser.add_argument("--outdir", default="data/output/03_reports/report")
    parser.add_argument("--config", default="config/dashboard.yaml")
    parser.add_argument("--source-runs-csv", default=None, help="Runs CSV used for diagnostics.")
    parser.add_argument("--source-roi-csv", default=None, help="ROI CSV used for dashboard-input merge.")
    parser.add_argument("--source-tornado-csv", default=None, help="Tornado CSV used for tornado/dollar inputs.")
    parser.add_argument(
        "--channel-scope",
        choices=["all"],
        default=None,
        help="Override analysis.channel_scope in dashboard config.",
    )
    parser.add_argument(
        "--scenario-selection",
        choices=["largest_total_abs_pct_non_fail", "largest_total_abs_pct", "first_non_baseline"],
        default=None,
        help="Override analysis.scenario_selection in dashboard config.",
    )
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="Remove existing generated files before regeneration.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    outdir = Path(args.outdir)
    cfg_path = Path(args.config)

    cfg = yaml.safe_load(cfg_path.read_text())
    if args.channel_scope:
        cfg.setdefault("analysis", {})
        cfg["analysis"]["channel_scope"] = args.channel_scope
    if args.scenario_selection:
        cfg.setdefault("analysis", {})
        cfg["analysis"]["scenario_selection"] = args.scenario_selection
    if not args.source_roi_csv:
        args.source_roi_csv = _infer_roi_source_csv(input_path)

    outdir.mkdir(parents=True, exist_ok=True)
    tables_dir = outdir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    if args.clean_output:
        clean_dirs = [tables_dir]
        figures_dir = outdir / "figures"
        if figures_dir.exists():
            shutil.rmtree(figures_dir)
        for d in clean_dirs:
            for p in d.iterdir():
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()

    df = load_results(input_path)
    metrics = compute_all_metrics(df, cfg, tables_dir)
    fig_paths = _empty_figure_paths()
    branding_cfg = cfg.get("branding", {})
    branding = {
        "cobrand_label": branding_cfg.get("cobrand_label", "UCSB x BlueAlpha AI"),
        "logos": {},
    }

    source_files = {
        "report_input": str(input_path),
        "runs_csv": args.source_runs_csv,
        "roi_csv": args.source_roi_csv,
        "tornado_csv": args.source_tornado_csv,
    }
    render_dashboard_payload(metrics, fig_paths, cfg, input_path, outdir, source_files, branding)

    _cleanup_legacy_report_outputs(outdir, "report.html")
    print("Dashboard payload and tables updated.")


if __name__ == "__main__":
    main()
