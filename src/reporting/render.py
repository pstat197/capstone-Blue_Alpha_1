from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def _fmt_money(x: float) -> str:
    v = float(x)
    sign = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1_000_000_000:
        return f"{sign}${av/1_000_000_000:.2f}B"
    if av >= 1_000_000:
        return f"{sign}${av/1_000_000:.2f}M"
    if av >= 1_000:
        return f"{sign}${av/1_000:.1f}K"
    return f"{sign}${av:,.2f}"


def _load_theory_block(cfg: dict) -> dict:
    theory_cfg = cfg.get("theory", {})
    if not bool(theory_cfg.get("enabled", True)):
        return {"available": False}

    source_tex = str(theory_cfg.get("source_tex", "docs/theory/prior-sensitivity-theory.tex"))
    tex_path = Path(source_tex)
    if not tex_path.exists():
        return {
            "available": False,
            "source_tex": source_tex,
            "reason": "Theory source file not found.",
        }

    raw = tex_path.read_text(encoding="utf-8", errors="ignore")
    raw = raw.replace("\ufeff", "")

    subsection_titles = [
        " ".join(s.strip().split())
        for s in re.findall(r"\\subsection\{([^}]*)\}", raw)
    ]
    max_subsections = int(theory_cfg.get("max_subsections", 8))
    subsection_titles = subsection_titles[:max_subsections]

    eq_raw = re.findall(r"\\begin\{equation\}(.*?)\\end\{equation\}", raw, flags=re.DOTALL)
    eq_labels = theory_cfg.get(
        "equation_labels",
        [
            "Observation model",
            "Channel prior",
            "Posterior (proportional form)",
            "Posterior mean shift",
            "Posterior precision decomposition",
            "Joint covariance under priors",
            "Signal allocation constraint",
            "Baseline ROI scale",
        ],
    )
    max_equations = int(theory_cfg.get("max_equations", 8))
    equations = []
    for i, eq in enumerate(eq_raw[:max_equations]):
        cleaned = " ".join(eq.replace("\n", " ").replace("\t", " ").split())
        cleaned = cleaned.replace("\u2014", "-").strip()
        equations.append(
            {
                "label": str(eq_labels[i]) if i < len(eq_labels) else f"Equation {i + 1}",
                "latex": cleaned,
            }
        )

    highlights = theory_cfg.get("highlights", [])
    if not highlights:
        highlights = [
            "Prior mean (mu) changes shift posterior channel effects by data-vs-prior weight.",
            "Prior variance (sigma) controls shrinkage strength and stability of attribution.",
            "Cross-channel movement is structural under joint posterior estimation with correlated channels.",
            "Sensitivity surfaces are read as response of ROI to hyperparameter perturbations.",
        ]

    return {
        "available": True,
        "title": str(theory_cfg.get("title", "Math Theory Linkage")),
        "source_tex": source_tex,
        "preview_equation": equations[0]["latex"] if equations else "",
        "highlights": highlights,
        "subsections": subsection_titles,
        "equations": equations,
    }


def render_html_report(
    metrics: dict,
    fig_paths: dict,
    cfg: dict,
    input_path: Path,
    outdir: Path,
    source_files: dict | None = None,
    branding: dict | None = None,
) -> None:
    template_dir = Path(__file__).resolve().parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("report_template.html")

    overview = metrics["overview"]
    scope = metrics.get("scope", {})
    diagnostics = metrics.get("diagnostics", {"available": False})
    dollar = metrics.get("dollar", {"available": False})
    scenario_snapshot = metrics.get("scenario_snapshot", {"available": False})

    linked_targets = scope.get("linked_targets", [])
    target_sets = scope.get("target_sets", [])
    mode = scope.get("mode", "unknown")
    scope_block = {
        "mode": mode,
        "mode_label": "Linked Targets" if mode == "linked_targets" else "Single/Mixed Targets",
        "linked_targets": linked_targets,
        "target_sets": target_sets,
        "channel_scope": scope.get("channel_scope", "all"),
        "channel_scope_label": scope.get("channel_scope_label", "All Modeled Channels"),
        "n_channels_before": scope.get("n_channels_before"),
        "n_channels_after": scope.get("n_channels_after"),
        "n_rows_before": scope.get("n_rows_before"),
        "n_rows_after": scope.get("n_rows_after"),
        "note": scope.get("note", ""),
    }

    meta = {
        "title": cfg["project"]["title"],
        "subtitle": cfg["project"]["subtitle"],
        "generated_at": overview["generated_at"],
        "input_file": str(input_path),
        "source_files": source_files or {"report_input": str(input_path)},
        "branding": branding or {"cobrand_label": "UCSB x BlueAlpha AI", "logos": {}},
        "authors": cfg["project"].get("authors", []),
    }

    methods = {
        "baseline_description": cfg.get("methods", {}).get(
            "baseline_description",
            "Baseline ROI is defined using the center of the tested prior grid.",
        ),
        "sensitivity_description": cfg.get("methods", {}).get(
            "sensitivity_description",
            "Sensitivity is measured by how much estimated ROI changes relative to baseline.",
        ),
        "visualization_description": cfg.get("methods", {}).get(
            "visualization_description",
            "Plots summarize the most sensitive settings and variation across the prior grid.",
        ),
    }
    intro_cfg = cfg.get("introduction", {})
    intro_block = {
        "title": intro_cfg.get("title", "Introduction"),
        "paragraphs": intro_cfg.get("paragraphs", []),
    }
    theory_block = _load_theory_block(cfg)
    appendix_tables = [
        "tables/baseline_table.csv",
        "tables/sensitivity_rank.csv",
        "tables/merged_with_pct_change.csv",
    ]
    if diagnostics.get("available"):
        appendix_tables.extend(
            [
                "tables/diagnostics_status_breakdown.csv",
                "tables/diagnostics_primary_checks.csv",
                "tables/diagnostics_flagged_channels.csv",
                "tables/diagnostics_check_matrix.csv",
            ]
        )
    if dollar.get("available"):
        appendix_tables.append("tables/dollar_sensitivity_rank.csv")
    if scenario_snapshot.get("available"):
        appendix_tables.append("tables/scenario_snapshot_rows.csv")

    rank_table_df = metrics["rank_top_df"].copy()
    if "baseline_roi" in rank_table_df.columns:
        rank_table_df["baseline_roi"] = rank_table_df["baseline_roi"].map(lambda x: f"{float(x):.4f}")
    if "max_abs_pct_change" in rank_table_df.columns:
        rank_table_df["max_abs_pct_change"] = rank_table_df["max_abs_pct_change"].map(
            lambda x: f"{float(x):.2f}%"
        )

    dollar_block = {"available": False}
    if dollar.get("available"):
        dollar_top_df = dollar["rank_top_df"].copy()
        if "left_dollar" in dollar_top_df.columns:
            dollar_top_df["left_dollar"] = dollar_top_df["left_dollar"].map(_fmt_money)
        if "right_dollar" in dollar_top_df.columns:
            dollar_top_df["right_dollar"] = dollar_top_df["right_dollar"].map(_fmt_money)
        if "max_abs_dollar_change" in dollar_top_df.columns:
            dollar_top_df["max_abs_dollar_change"] = dollar_top_df["max_abs_dollar_change"].map(_fmt_money)
        if "median_dollar_change" in dollar_top_df.columns:
            dollar_top_df["median_dollar_change"] = dollar_top_df["median_dollar_change"].map(_fmt_money)
        dollar_block = {
            "available": True,
            "range_mode": dollar.get("range_mode", "p05p95"),
            "source": dollar.get("source", ""),
            "dollars_per_subscription_note": dollar.get("dollars_per_subscription_note", "unknown"),
            "quick_lines": dollar.get("quick_lines", []),
            "rank_rows": dollar_top_df.to_dict(orient="records"),
        }

    scenario_block = {"available": False}
    if scenario_snapshot.get("available"):
        snap_top_n = int(cfg.get("figures", {}).get("scenario_snapshot_top_n", 8))
        fig_items = fig_paths.get("scenario_snapshots", [])
        fig_by_run = {str(x.get("run_id")): f"figures/{x.get('path')}" for x in fig_items}

        scenario_items = []
        for item in scenario_snapshot.get("scenarios", []):
            run_id = str(item.get("run_id", ""))
            snap_df = item["rows_df"].copy()
            if snap_top_n > 0:
                snap_df = snap_df.head(snap_top_n)

            if "pct_change" in snap_df.columns:
                snap_df["pct_change"] = snap_df["pct_change"].map(lambda x: f"{float(x):.2f}%")
            if "delta_value_used" in snap_df.columns:
                snap_df["delta_value_used"] = snap_df["delta_value_used"].map(
                    lambda x: _fmt_money(float(x)) if str(x).strip().lower() not in {"nan", "none", ""} else "NA"
                )
            if "estimated_roi" in snap_df.columns:
                snap_df["estimated_roi"] = snap_df["estimated_roi"].map(lambda x: f"{float(x):.4f}")
            if "baseline_roi" in snap_df.columns:
                snap_df["baseline_roi"] = snap_df["baseline_roi"].map(lambda x: f"{float(x):.4f}")

            keep_cols = [
                c
                for c in ["channel", "estimated_roi", "baseline_roi", "pct_change", "delta_value_used"]
                if c in snap_df.columns
            ]
            scenario_items.append(
                {
                    "run_id": run_id,
                    "label": item.get("label", run_id),
                    "meta": item.get("meta", {}),
                    "n_channels": item.get("n_channels", 0),
                    "n_rows": item.get("n_rows", 0),
                    "figure": fig_by_run.get(run_id),
                    "rows": snap_df[keep_cols].to_dict(orient="records"),
                }
            )

        scenario_block = {
            "available": True,
            "selection_mode": scenario_snapshot.get("selection_mode", ""),
            "selection_reason": scenario_snapshot.get("selection_reason", ""),
            "selected_run_id": str(scenario_snapshot.get("selected_run_id", "")),
            "selected_meta": scenario_snapshot.get("selected_meta", {}),
            "n_channels": scenario_snapshot.get("n_channels", 0),
            "scenario_count": int(scenario_snapshot.get("scenario_count", len(scenario_items))),
            "scenarios": scenario_items,
        }

    html = template.render(
        meta=meta,
        methods=methods,
        introduction=intro_block,
        theory=theory_block,
        scope=scope_block,
        overview=overview,
        diagnostics=diagnostics,
        dollar=dollar_block,
        scenario_snapshot=scenario_block,
        quick_overview_lines=metrics.get("quick_overview_lines", []),
        rank_table=rank_table_df.to_dict(orient="records"),
        recommendations=metrics["recommendations"],
        figures={
            "tornado": f"figures/{fig_paths['tornado']}" if fig_paths.get("tornado") else None,
            "tornado_dollar": (
                f"figures/{fig_paths['tornado_dollar']}" if fig_paths.get("tornado_dollar") else None
            ),
            "scenario_snapshot": (
                f"figures/{fig_paths['scenario_snapshot']}" if fig_paths.get("scenario_snapshot") else None
            ),
        },
        heatmap_pages=fig_paths.get("heatmap_pages", []),
        heatmap_modes=fig_paths.get("heatmap_modes", []),
        default_heatmap_mode=fig_paths.get("default_heatmap_mode"),
        appendix_tables=appendix_tables,
    )

    out_path = outdir / cfg["output"]["report_filename"]
    out_path.write_text(html, encoding="utf-8")
