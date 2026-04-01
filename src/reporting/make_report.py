from __future__ import annotations
import argparse
import shutil
from pathlib import Path
import yaml

try:
    from .io_load import load_results
    from .metrics import compute_all_metrics
    from .figures import make_all_figures
    from .render import render_html_report
except ImportError:  # Allow direct script execution.
    from io_load import load_results
    from metrics import compute_all_metrics
    from figures import make_all_figures
    from render import render_html_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="data/output/02_tables/all_channels/prior_sensitivity_results_all_channels.csv",
    )
    parser.add_argument("--outdir", default="data/output/03_reports/report")
    parser.add_argument("--config", default="config/report_google_meta_tiktok.yaml")
    parser.add_argument("--source-runs-csv", default=None, help="Runs CSV used for diagnostics.")
    parser.add_argument("--source-roi-csv", default=None, help="ROI CSV used for report-input merge.")
    parser.add_argument("--source-tornado-csv", default=None, help="Tornado CSV used for tornado/dollar inputs.")
    parser.add_argument(
        "--channel-scope",
        choices=["all"],
        default=None,
        help="Override analysis.channel_scope in report config.",
    )
    parser.add_argument(
        "--scenario-selection",
        choices=["largest_total_abs_pct_non_fail", "largest_total_abs_pct", "first_non_baseline"],
        default=None,
        help="Override analysis.scenario_selection in report config.",
    )
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="Remove existing files under outdir/figures and outdir/tables before regeneration.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    outdir = Path(args.outdir)
    cfg_path = Path(args.config)

    outdir.mkdir(parents=True, exist_ok=True)
    figures_dir = outdir / "figures"
    tables_dir = outdir / "tables"
    assets_dir = outdir / "assets"
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    if args.clean_output:
        for d in (figures_dir, tables_dir, assets_dir):
            for p in d.iterdir():
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()

    cfg = yaml.safe_load(cfg_path.read_text())
    if args.channel_scope:
        cfg.setdefault("analysis", {})
        cfg["analysis"]["channel_scope"] = args.channel_scope
    if args.scenario_selection:
        cfg.setdefault("analysis", {})
        cfg["analysis"]["scenario_selection"] = args.scenario_selection

    df = load_results(input_path)
    metrics = compute_all_metrics(df, cfg, tables_dir)
    fig_paths = make_all_figures(df, metrics, cfg, figures_dir)
    branding_cfg = cfg.get("branding", {})
    branding = {
        "cobrand_label": branding_cfg.get("cobrand_label", "UCSB x BlueAlpha AI"),
        "logos": {},
    }
    logo_cfg = branding_cfg.get("logos", {})
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
    render_html_report(metrics, fig_paths, cfg, input_path, outdir, source_files, branding)

    print(f"Report written to: {outdir / cfg['output']['report_filename']}")


if __name__ == "__main__":
    main()
