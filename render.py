from __future__ import annotations
from pathlib import Path
from jinja2 import Environment, FileSystemLoader


def render_html_report(metrics: dict, fig_paths: dict, cfg: dict, input_path: Path, outdir: Path) -> None:
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("report_template.html")

    overview = metrics["overview"]
    meta = {
        "title": cfg["project"]["title"],
        "subtitle": cfg["project"]["subtitle"],
        "generated_at": overview["generated_at"],
        "input_file": str(input_path),
        "authors": cfg["project"].get("authors", []),
    }

    methods = {
        "baseline_description": cfg.get("methods", {}).get(
            "baseline_description",
            "Baseline ROI is defined using the center of the tested prior grid."
        ),
        "sensitivity_description": cfg.get("methods", {}).get(
            "sensitivity_description",
            "Sensitivity is measured by how much estimated ROI changes relative to baseline."
        ),
        "visualization_description": cfg.get("methods", {}).get(
            "visualization_description",
            "Plots summarize the most sensitive settings and variation across the prior grid."
        ),
    }

    sections = []
    rank = metrics["rank_df"]
    for r in rank.itertuples(index=False):
        hm_path = fig_paths["per_target"].get((r.target_channel, r.roi_prior_dist))
        sections.append(
            {
                "title": f"{r.target_channel} — {r.roi_prior_dist}",
                "baseline_roi": f"{r.baseline_roi:.4f}",
                "max_abs_pct_change": f"{r.max_abs_pct_change:.2f}%",
                "heatmaps": [{"caption": "mu × sigma (% change)", "path": hm_path}] if hm_path else [],
            }
        )

    html = template.render(
        meta=meta,
        methods=methods,
        overview=overview,
        quick_overview_lines=metrics.get("quick_overview_lines", []),
        rank_table=metrics["rank_top_df"].to_dict(orient="records"),
        recommendations=metrics["recommendations"],
        figures={
            "tornado": f"figures/{fig_paths['tornado']}" if fig_paths.get("tornado") else None
        },
        per_target_sections=sections,
        appendix_tables=[
            "tables/baseline_table.csv",
            "tables/sensitivity_rank.csv",
            "tables/merged_with_pct_change.csv",
        ],
    )

    out_path = outdir / cfg["output"]["report_filename"]
    out_path.write_text(html, encoding="utf-8")