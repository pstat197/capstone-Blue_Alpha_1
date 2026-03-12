from __future__ import annotations
import argparse
from pathlib import Path
import yaml

from io_load import load_results
from metrics import compute_all_metrics
from figures import make_all_figures
from render import render_html_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="input/prior_sensitivity_results_all_channels.csv")
    parser.add_argument("--outdir", default="output")
    parser.add_argument("--config", default="config/report_config.yaml")
    args = parser.parse_args()

    input_path = Path(args.input)
    outdir = Path(args.outdir)
    cfg_path = Path(args.config)

    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "figures").mkdir(parents=True, exist_ok=True)
    (outdir / "tables").mkdir(parents=True, exist_ok=True)

    cfg = yaml.safe_load(cfg_path.read_text())

    df = load_results(input_path)
    metrics = compute_all_metrics(df, cfg, outdir / "tables")
    fig_paths = make_all_figures(df, metrics, cfg, outdir / "figures")
    render_html_report(metrics, fig_paths, cfg, input_path, outdir)

    print(f"Report written to: {outdir / cfg['output']['report_filename']}")


if __name__ == "__main__":
    main()
