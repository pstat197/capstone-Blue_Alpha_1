from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd
import yaml

try:
    from .metrics import compute_all_metrics
    from .figures import make_all_figures
    from .render import render_dashboard_output
    from src.viz.roi_prior_vs_posterior import make_plot as make_roi_prior_vs_posterior_plot
except ImportError:  # Allow direct script execution.
    from metrics import compute_all_metrics
    from figures import make_all_figures
    from render import render_dashboard_output
    from src.viz.roi_prior_vs_posterior import make_plot as make_roi_prior_vs_posterior_plot


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
    "spend_vs_effect_onepager.png",
    "structural_adstock_curves.png",
    "structural_saturation_curves.png",
    "structural_carryover_decomposition.png",
}


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
    report_path = outdir / report_filename
    if report_path.exists() and report_path.is_file():
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


def load_results(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    missing = _REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
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
        help="Remove existing generated files before regeneration, while preserving figures/meridian_official.",
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

    output_cfg = cfg.setdefault("output", {})
    write_dashboard = bool(output_cfg.get("write_dashboard", True))
    write_report = bool(output_cfg.get("write_report", False))
    report_filename = str(output_cfg.get("report_filename", "report.html"))
    cleanup_report_outputs = bool(output_cfg.get("cleanup_report_outputs", True))

    outdir.mkdir(parents=True, exist_ok=True)
    tables_dir = outdir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    figures_dir = outdir / "figures"
    if write_report:
        figures_dir.mkdir(parents=True, exist_ok=True)

    assets_dir = outdir / "assets"
    if write_report:
        assets_dir.mkdir(parents=True, exist_ok=True)

    if args.clean_output:
        clean_dirs = [tables_dir]
        if figures_dir.exists():
            clean_dirs.append(figures_dir)
        if assets_dir.exists():
            clean_dirs.append(assets_dir)
        for d in clean_dirs:
            for p in d.iterdir():
                if d == figures_dir and p.is_dir() and p.name == "meridian_official":
                    continue
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()

    df = load_results(input_path)
    metrics = compute_all_metrics(df, cfg, tables_dir)
    fig_paths = make_all_figures(df, metrics, cfg, figures_dir) if write_report else _empty_figure_paths()
    if args.source_roi_csv:
        figures_dir.mkdir(parents=True, exist_ok=True)
        roi_prior_plot_path = figures_dir / "roi_prior_vs_posterior.png"
        make_roi_prior_vs_posterior_plot(
            args.source_roi_csv,
            roi_prior_plot_path,
            title="ROI Prior vs Posterior with 50% Posterior Intervals",
        )
        fig_paths["roi_prior_vs_posterior"] = roi_prior_plot_path.name
    branding_cfg = cfg.get("branding", {})
    branding = {
        "cobrand_label": branding_cfg.get("cobrand_label", "UCSB x BlueAlpha AI"),
        "logos": {},
    }
    logo_cfg = branding_cfg.get("logos", {})
    if write_report:
        for key in ["ucsb", "bluealpha"]:
            raw = logo_cfg.get(key)
            if not raw:
                continue
            src = Path(raw)
            if not src.exists():
                continue
            dst = assets_dir / src.name
            shutil.copy2(src, dst)
            branding["logos"][key] = f"assets/{dst.name}"

    source_files = {
        "report_input": str(input_path),
        "runs_csv": args.source_runs_csv,
        "roi_csv": args.source_roi_csv,
        "tornado_csv": args.source_tornado_csv,
    }
    render_dashboard_output(metrics, fig_paths, cfg, input_path, outdir, source_files, branding)

    if (not write_report) and cleanup_report_outputs:
        _cleanup_legacy_report_outputs(outdir, report_filename)

    if write_dashboard:
        print("Dashboard updated.")
    elif write_report:
        print("Report updated.")
    else:
        print("Dashboard tables updated.")


if __name__ == "__main__":
    main()
