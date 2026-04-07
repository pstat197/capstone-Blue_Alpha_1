from __future__ import annotations

import json
import math
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



def _is_missing_value(x) -> bool:
    if x is None:
        return True
    if isinstance(x, str):
        s = x.strip().lower()
        return s in {"", "nan", "na", "n/a", "none", "null"}
    try:
        return math.isnan(float(x))
    except Exception:
        return False


def _fmt_float_safe(x, digits: int = 6, missing_label: str = "-") -> str:
    if _is_missing_value(x):
        return missing_label
    return f"{float(x):.{digits}f}"


def _to_float_safe(x) -> float | None:
    if _is_missing_value(x):
        return None
    if isinstance(x, str):
        cleaned = re.sub(r"[^0-9eE+\-.]", "", x.strip())
        if cleaned in {"", "-", "+", ".", "-.", "+."}:
            return None
        try:
            return float(cleaned)
        except Exception:
            return None
    try:
        return float(x)
    except Exception:
        return None


def _clean_text_safe(x, missing_label: str = "-") -> str:
    if _is_missing_value(x):
        return missing_label
    return str(x).strip()


def _truncate_text(s: str, max_len: int = 58) -> str:
    text = str(s)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "..."

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
    qc_gate = metrics.get("qc_gate", {"available": False})
    decision_card = metrics.get("decision_card", {"available": False})
    prior_guardrail = metrics.get("prior_guardrail", {"available": False})
    dollar = metrics.get("dollar", {"available": False})
    scenario_snapshot = metrics.get("scenario_snapshot", {"available": False})
    spend_effect = metrics.get("spend_effect", {"available": False})
    structural = metrics.get("structural", {"available": False})
    presentation_cfg = cfg.get("presentation", {}) or {}
    diagnostics_level = str(presentation_cfg.get("diagnostics_level", "concise")).strip().lower()
    structural_level = str(presentation_cfg.get("structural_level", "concise")).strip().lower()
    qc_gate_level = str(presentation_cfg.get("qc_gate_level", "concise")).strip().lower()
    show_sources = bool(presentation_cfg.get("show_sources", False))
    if diagnostics_level not in {"hide", "concise", "full"}:
        diagnostics_level = "concise"
    if structural_level not in {"hide", "concise", "full"}:
        structural_level = "concise"
    if qc_gate_level not in {"concise", "full"}:
        qc_gate_level = "concise"
    display_block = {
        "diagnostics_level": diagnostics_level,
        "structural_level": structural_level,
        "qc_gate_level": qc_gate_level,
        "show_sources": show_sources,
    }

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
    if prior_guardrail.get("available"):
        appendix_tables.append("tables/prior_guardrail_summary.csv")
        appendix_tables.append("tables/prior_guardrail_by_channel.csv")
        if prior_guardrail.get("top_fail_rows"):
            appendix_tables.append("tables/prior_guardrail_top_fail_rows.csv")
    if qc_gate.get("available"):
        appendix_tables.extend(
            [
                "tables/qc_gate_run_subset.csv",
                "tables/qc_gate_status_breakdown.csv",
            ]
        )
        if qc_gate.get("rank_rows"):
            appendix_tables.append("tables/qc_gate_channel_sensitivity.csv")
    if dollar.get("available"):
        appendix_tables.append("tables/dollar_sensitivity_rank.csv")
    if scenario_snapshot.get("available"):
        appendix_tables.append("tables/scenario_snapshot_rows.csv")
    if spend_effect.get("available"):
        appendix_tables.append("tables/spend_vs_effect_table.csv")
    if structural.get("available"):
        appendix_tables.extend(
            [
                "tables/structural_run_table.csv",
                "tables/structural_profile_table.csv",
                "tables/structural_adstock_curve_table.csv",
                "tables/structural_saturation_curve_table.csv",
                "tables/structural_carryover_by_channel.csv",
            ]
        )

    rank_table_raw_df = metrics["rank_df"].copy()
    rank_table_df = rank_table_raw_df.copy()
    if "baseline_roi" in rank_table_df.columns:
        rank_table_df["baseline_roi"] = rank_table_df["baseline_roi"].map(lambda x: f"{float(x):.4f}")
    if "max_abs_pct_change" in rank_table_df.columns:
        rank_table_df["max_abs_pct_change"] = rank_table_df["max_abs_pct_change"].map(
            lambda x: f"{float(x):.2f}%"
        )
    if "max_abs_delta_roi" in rank_table_df.columns:
        rank_table_df["max_abs_delta_roi"] = rank_table_df["max_abs_delta_roi"].map(
            lambda x: f"{float(x):.4f}"
        )

    if "primary_metric" in rank_table_df.columns:
        rank_table_df["ranking_metric"] = rank_table_df["primary_metric"].map(
            lambda m: "Max |% Change|" if str(m) == "pct_change" else "Max |Delta ROI|"
        )
        rank_table_df["max_change_display"] = rank_table_df.apply(
            lambda r: (
                f"{float(r.get('primary_value')):.2f}%"
                if str(r.get("primary_metric")) == "pct_change"
                else f"{float(r.get('primary_value')):.4f}"
            ),
            axis=1,
        )
    else:
        rank_table_df["ranking_metric"] = "Max |% Change|"
        rank_table_df["max_change_display"] = rank_table_df.get("max_abs_pct_change", "NA")

    if "pct_metric_reliable" in rank_table_df.columns:
        rank_table_df["baseline_stability"] = rank_table_df["pct_metric_reliable"].map(
            lambda v: "Stable" if bool(v) else "Unstable"
        )
    else:
        rank_table_df["baseline_stability"] = "NA"

    top_n = int((cfg.get("ranking", {}) or {}).get("top_n", 10))
    if "pct_metric_reliable" in rank_table_df.columns:
        stable_rank_df = rank_table_df[rank_table_df["pct_metric_reliable"] == True].copy()  # noqa: E712
        unstable_rank_df = rank_table_df[rank_table_df["pct_metric_reliable"] != True].copy()  # noqa: E712
        rank_table_exec_df = stable_rank_df.head(top_n).copy()
        if rank_table_exec_df.empty:
            rank_table_exec_df = rank_table_df.head(top_n).copy()
            exec_table_mode = "all_pairs_fallback"
        else:
            exec_table_mode = "stable_only"
    else:
        unstable_rank_df = rank_table_df.iloc[0:0].copy()
        rank_table_exec_df = rank_table_df.head(top_n).copy()
        exec_table_mode = "all_pairs"

    unstable_preview_n = 5
    rank_table_unstable_preview_df = unstable_rank_df.head(unstable_preview_n).copy()

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
    qc_gate_block = {"available": False}
    if qc_gate.get("available"):
        run_rows = []
        for idx, row in enumerate(qc_gate.get("run_rows", []), start=1):
            status = _clean_text_safe(row.get("qc_status_code"), "UNKNOWN")
            primary_check = _clean_text_safe(row.get("qc_primary_review_check"), "")
            if primary_check == "-":
                primary_check = ""
            flagged_channels = _clean_text_safe(row.get("qc_flagged_channels"), "")
            if flagged_channels == "-":
                flagged_channels = ""
            baseline_neg_prob = (
                None
                if _is_missing_value(row.get("qc_baseline_neg_prob"))
                else f"{float(row.get('qc_baseline_neg_prob')):.2f}"
            )

            notes_parts = []
            if primary_check:
                notes_parts.append(f"check: {primary_check}")
            if flagged_channels:
                notes_parts.append(f"flags: {flagged_channels}")
            if baseline_neg_prob is not None:
                notes_parts.append(f"baseline neg prob: {baseline_neg_prob}")
            review_notes = (
                "; ".join(notes_parts)
                if notes_parts
                else ("all core checks pass" if status == "PASS" else "no additional notes")
            )

            run_id_text = _clean_text_safe(row.get("run_id"), "")
            run_rows.append(
                {
                    "scenario_id": f"Q{idx}",
                    "run_id": run_id_text,
                    "run_id_short": _truncate_text(run_id_text, max_len=64) if run_id_text else "",
                    "roi_prior_mu": _fmt_float_safe(row.get("roi_prior_mu"), digits=6),
                    "roi_prior_sigma": _fmt_float_safe(row.get("roi_prior_sigma"), digits=6),
                    "roi_prior_dist": _clean_text_safe(row.get("roi_prior_dist"), "-"),
                    "qc_status_code": status,
                    "review_notes": review_notes,
                }
            )

        rank_rows = []
        for row in qc_gate.get("rank_rows", []):
            rank_rows.append(
                {
                    "channel": row.get("channel"),
                    "max_change": (
                        "NA"
                        if row.get("max_change") is None
                        else _fmt_money(float(row.get("max_change")))
                        if qc_gate.get("rank_metric") == "delta_value_abs"
                        else f"{float(row.get('max_change')):.4f}"
                    ),
                    "median_change": (
                        "NA"
                        if row.get("median_change") is None
                        else _fmt_money(float(row.get("median_change")))
                        if qc_gate.get("rank_metric") == "delta_value_abs"
                        else f"{float(row.get('median_change')):.4f}"
                    ),
                    "n": int(row.get("n", 0) or 0),
                }
            )

        qc_gate_block = {
            "available": True,
            "result": qc_gate.get("result", "REVIEW"),
            "mu_values": [_fmt_float_safe(v, digits=6, missing_label="NA") for v in qc_gate.get("mu_values", [])],
            "sigma_values": [_fmt_float_safe(v, digits=6, missing_label="NA") for v in qc_gate.get("sigma_values", [])],
            "dists": qc_gate.get("dists", []),
            "overview": qc_gate.get("overview", {}),
            "status_rows": qc_gate.get("status_rows", []),
            "run_rows": run_rows,
            "rank_metric": qc_gate.get("rank_metric"),
            "rank_rows": rank_rows,
            "quick_lines": qc_gate.get("quick_lines", []),
        }

    decision_card_block = {"available": False}
    if decision_card.get("available"):
        tier = str(decision_card.get("tier", "YELLOW")).upper()
        tier_class = {
            "GREEN": "pass",
            "YELLOW": "review",
            "RED": "fail",
        }.get(tier, "review")
        decision_card_block = {
            "available": True,
            "tier": tier,
            "tier_class": tier_class,
            "headline": _clean_text_safe(decision_card.get("headline"), ""),
            "score_label": _clean_text_safe(decision_card.get("score_label"), ""),
            "score_value": _clean_text_safe(decision_card.get("score_value"), ""),
            "policy_name": _clean_text_safe(decision_card.get("policy_name"), ""),
            "policy_rules": decision_card.get("policy_rules", []),
            "triggered_rules": decision_card.get("triggered_rules", []),
            "reasons": decision_card.get("reasons", []),
            "actions": decision_card.get("actions", []),
        }

    spend_effect_block = {"available": False}
    if spend_effect.get("available"):
        table_df = spend_effect.get("table_df", None)
        rows = []
        if table_df is not None and not table_df.empty:
            for row in table_df.to_dict(orient="records"):
                rows.append(
                    {
                        "channel": str(row.get("channel", "")),
                        "spend_share_pct": (
                            "NA"
                            if row.get("spend_share_pct") is None
                            else f"{float(row.get('spend_share_pct')):.1f}%"
                        ),
                        "effect_share_pct": (
                            "NA"
                            if row.get("effect_share_pct") is None
                            else f"{float(row.get('effect_share_pct')):.1f}%"
                        ),
                        "share_gap_pp": (
                            "NA"
                            if row.get("share_gap_pp") is None
                            else f"{float(row.get('share_gap_pp')):+.1f} pp"
                        ),
                        "estimated_roi": (
                            "NA"
                            if row.get("estimated_roi") is None
                            else f"{float(row.get('estimated_roi')):.4f}"
                        ),
                        "effect_negative": bool(row.get("effect_negative", False)),
                    }
                )

        max_gap = spend_effect.get("max_gap_row") or {}
        spend_effect_block = {
            "available": True,
            "selected_run_id": spend_effect.get("selected_run_id", ""),
            "spend_source": spend_effect.get("spend_source", ""),
            "effect_source": spend_effect.get("effect_source", ""),
            "n_negative_effect_channels": int(spend_effect.get("n_negative_effect_channels", 0) or 0),
            "max_gap_channel": max_gap.get("channel"),
            "max_gap_pp": (
                None
                if max_gap.get("share_gap_pp") is None
                else float(max_gap.get("share_gap_pp"))
            ),
            "rows": rows,
        }

    scenario_block = {"available": False}
    if scenario_snapshot.get("available"):
        snap_top_n = int(cfg.get("figures", {}).get("scenario_snapshot_top_n", 8))
        fig_items = fig_paths.get("scenario_snapshots", [])
        fig_by_run = {str(x.get("run_id")): f"figures/{x.get('path')}" for x in fig_items}

        scenario_items = []
        max_runs = int(cfg.get("figures", {}).get("scenario_snapshot_max_runs", 6))
        source_scenarios = scenario_snapshot.get("scenarios", [])
        if max_runs > 0:
            source_scenarios = source_scenarios[:max_runs]
        for item in source_scenarios:
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
            "scenario_count": int(len(scenario_items)),
            "scenarios": scenario_items,
        }

    structural_block = {"available": False}
    if structural.get("available"):
        profile_rows = []
        for row in structural.get("profile_rows", []):
            profile_rows.append(
                {
                    "struct_profile_id": row.get("struct_profile_id"),
                    "adstock_alpha_m": ("NA" if row.get("adstock_alpha_m") is None else f"{float(row.get('adstock_alpha_m')):.3f}"),
                    "saturation_ec_m": ("NA" if row.get("saturation_ec_m") is None else f"{float(row.get('saturation_ec_m')):.3f}"),
                    "saturation_slope_m": ("NA" if row.get("saturation_slope_m") is None else f"{float(row.get('saturation_slope_m')):.3f}"),
                    "max_lag": ("NA" if row.get("max_lag") is None else str(int(float(row.get("max_lag"))))),
                    "adstock_decay_spec": row.get("adstock_decay_spec"),
                    "immediate_share": ("NA" if row.get("immediate_share") is None else f"{100.0*float(row.get('immediate_share')):.1f}%"),
                    "carryover_share": ("NA" if row.get("carryover_share") is None else f"{100.0*float(row.get('carryover_share')):.1f}%"),
                    "avg_lag": ("NA" if row.get("avg_lag") is None else f"{float(row.get('avg_lag')):.2f}"),
                    "half_life_lag": ("NA" if row.get("half_life_lag") is None else f"{float(row.get('half_life_lag')):.2f}"),
                    "n_runs": int(row.get("n_runs", 0) or 0),
                }
            )

        run_rows = []
        for row in structural.get("run_rows", []):
            run_rows.append(
                {
                    "run_id": row.get("run_id"),
                    "roi_prior_mu": ("NA" if row.get("roi_prior_mu") is None else f"{float(row.get('roi_prior_mu')):.6f}"),
                    "roi_prior_sigma": ("NA" if row.get("roi_prior_sigma") is None else f"{float(row.get('roi_prior_sigma')):.6f}"),
                    "roi_prior_dist": row.get("roi_prior_dist"),
                    "adstock_alpha_m": ("NA" if row.get("adstock_alpha_m") is None else f"{float(row.get('adstock_alpha_m')):.3f}"),
                    "saturation_ec_m": ("NA" if row.get("saturation_ec_m") is None else f"{float(row.get('saturation_ec_m')):.3f}"),
                    "saturation_slope_m": ("NA" if row.get("saturation_slope_m") is None else f"{float(row.get('saturation_slope_m')):.3f}"),
                    "max_lag": ("NA" if row.get("max_lag") is None else str(int(float(row.get("max_lag"))))),
                    "adstock_decay_spec": row.get("adstock_decay_spec"),
                    "qc_status_code": row.get("qc_status_code"),
                    "is_baseline": bool(row.get("is_baseline", False)),
                    "total_abs_pct_change": ("NA" if row.get("total_abs_pct_change") is None else f"{float(row.get('total_abs_pct_change')):.2f}"),
                }
            )

        selected_profile = structural.get("selected_profile") or {}
        structural_block = {
            "available": True,
            "selected_run_id": structural.get("selected_run_id"),
            "selected_profile_id": selected_profile.get("struct_profile_id"),
            "notes": structural.get("notes", []),
            "profile_rows": profile_rows,
            "run_rows": run_rows,
        }

    diagnostics_focus = []
    if diagnostics.get("available"):
        overview_diag = diagnostics.get("overview", {}) or {}
        n_fail = int(overview_diag.get("fail_runs", 0) or 0)
        n_review = int(overview_diag.get("review_runs", 0) or 0)
        if n_fail == 0 and n_review == 0:
            diagnostics_focus.append("All explored runs passed diagnostics.")
        else:
            diagnostics_focus.append(
                f"{n_fail} fail and {n_review} review run(s) were observed in broad exploration."
            )
            diagnostics_focus.append(
                "These diagnostics are used to define safe default windows; out-of-window runs are not used as defaults."
            )
        primary_rows = diagnostics.get("primary_rows") or []
        if primary_rows:
            first = primary_rows[0]
            diagnostics_focus.append(
                f"Main issue driver: {first.get('check', 'unknown')} ({int(first.get('count', 0) or 0)} run(s))."
            )

    rank_dashboard_rows = []
    for row in rank_table_raw_df.to_dict(orient="records"):
        primary_metric = str(row.get("primary_metric", "pct_change"))
        primary_value = _to_float_safe(row.get("primary_value"))
        if primary_value is None:
            primary_value = _to_float_safe(row.get("max_abs_pct_change"))
        rank_dashboard_rows.append(
            {
                "channel": _clean_text_safe(row.get("channel"), "unknown"),
                "roi_prior_dist": _clean_text_safe(row.get("roi_prior_dist"), "Unknown"),
                "baseline_roi": _to_float_safe(row.get("baseline_roi")),
                "max_abs_pct_change": _to_float_safe(row.get("max_abs_pct_change")),
                "max_abs_delta_roi": _to_float_safe(row.get("max_abs_delta_roi")),
                "primary_metric": primary_metric,
                "primary_value": primary_value,
                "pct_metric_reliable": bool(row.get("pct_metric_reliable", True)),
            }
        )

    spend_effect_dashboard_rows = []
    table_df_dashboard = spend_effect.get("table_df", None)
    if table_df_dashboard is not None and not table_df_dashboard.empty:
        for row in table_df_dashboard.to_dict(orient="records"):
            spend_effect_dashboard_rows.append(
                {
                    "channel": _clean_text_safe(row.get("channel"), "unknown"),
                    "spend_share_pct": _to_float_safe(row.get("spend_share_pct")),
                    "effect_share_pct": _to_float_safe(row.get("effect_share_pct")),
                    "share_gap_pp": _to_float_safe(row.get("share_gap_pp")),
                    "estimated_roi": _to_float_safe(row.get("estimated_roi")),
                    "effect_negative": bool(row.get("effect_negative", False)),
                }
            )

    scenario_dashboard_items = []
    for item in scenario_block.get("scenarios", []):
        rows = []
        for row in item.get("rows", []):
            rows.append(
                {
                    "channel": _clean_text_safe(row.get("channel"), "unknown"),
                    "estimated_roi": _to_float_safe(row.get("estimated_roi")),
                    "baseline_roi": _to_float_safe(row.get("baseline_roi")),
                    "pct_change": _to_float_safe(row.get("pct_change")),
                    "delta_value_used": _clean_text_safe(row.get("delta_value_used"), "NA"),
                }
            )
        scenario_dashboard_items.append(
            {
                "run_id": _clean_text_safe(item.get("run_id"), ""),
                "label": _clean_text_safe(item.get("label"), ""),
                "n_channels": int(item.get("n_channels", 0) or 0),
                "rows": rows,
            }
        )

    dashboard_payload = {
        "meta": {
            "title": meta.get("title", "Report"),
            "subtitle": meta.get("subtitle", ""),
            "generated_at": meta.get("generated_at", ""),
            "authors": meta.get("authors", []),
        },
        "overview": {
            "n_rows": int(overview.get("n_rows", 0) or 0),
            "n_channels": int(overview.get("n_channels", 0) or 0),
            "n_dists": int(overview.get("n_dists", 0) or 0),
            "n_target_sets": int(overview.get("n_target_sets", 0) or 0),
        },
        "thresholds": cfg.get("thresholds", {}),
        "decision_card": decision_card_block,
        "diagnostics_overview": diagnostics.get("overview", {}),
        "rank_rows": rank_dashboard_rows,
        "spend_effect_rows": spend_effect_dashboard_rows,
        "scenario_items": scenario_dashboard_items,
        "quick_overview_lines": metrics.get("quick_overview_lines", []),
        "recommendations": metrics.get("recommendations", []),
        "figures": {
            "tornado": f"figures/{fig_paths['tornado']}" if fig_paths.get("tornado") else None,
            "tornado_dollar": (
                f"figures/{fig_paths['tornado_dollar']}" if fig_paths.get("tornado_dollar") else None
            ),
            "spend_effect": (
                f"figures/{fig_paths['spend_effect']}" if fig_paths.get("spend_effect") else None
            ),
            "adstock_curves": (
                f"figures/{fig_paths['adstock_curves']}" if fig_paths.get("adstock_curves") else None
            ),
            "saturation_curves": (
                f"figures/{fig_paths['saturation_curves']}" if fig_paths.get("saturation_curves") else None
            ),
            "carryover_decomposition": (
                f"figures/{fig_paths['carryover_decomposition']}" if fig_paths.get("carryover_decomposition") else None
            ),
            "scenario_snapshot": (
                f"figures/{fig_paths['scenario_snapshot']}" if fig_paths.get("scenario_snapshot") else None
            ),
        },
        "heatmap_pages": [f"figures/{x}" for x in fig_paths.get("heatmap_pages", [])],
        "heatmap_modes": fig_paths.get("heatmap_modes", []),
        "default_heatmap_mode": fig_paths.get("default_heatmap_mode"),
    }
    html = template.render(
        meta=meta,
        methods=methods,
        introduction=intro_block,
        theory=theory_block,
        scope=scope_block,
        overview=overview,
        diagnostics=diagnostics,
        diagnostics_focus=diagnostics_focus,
        qc_gate=qc_gate_block,
        decision_card=decision_card_block,
        dollar=dollar_block,
        scenario_snapshot=scenario_block,
        spend_effect=spend_effect_block,
        structural=structural_block,
        display=display_block,
        quick_overview_lines=metrics.get("quick_overview_lines", []),
        rank_table=rank_table_exec_df.to_dict(orient="records"),
        rank_table_unstable=rank_table_unstable_preview_df.to_dict(orient="records"),
        exec_table_mode=exec_table_mode,
        recommendations=metrics["recommendations"],
        figures={
            "tornado": f"figures/{fig_paths['tornado']}" if fig_paths.get("tornado") else None,
            "tornado_dollar": (
                f"figures/{fig_paths['tornado_dollar']}" if fig_paths.get("tornado_dollar") else None
            ),
            "spend_effect": (
                f"figures/{fig_paths['spend_effect']}" if fig_paths.get("spend_effect") else None
            ),
            "adstock_curves": (
                f"figures/{fig_paths['adstock_curves']}" if fig_paths.get("adstock_curves") else None
            ),
            "saturation_curves": (
                f"figures/{fig_paths['saturation_curves']}" if fig_paths.get("saturation_curves") else None
            ),
            "carryover_decomposition": (
                f"figures/{fig_paths['carryover_decomposition']}" if fig_paths.get("carryover_decomposition") else None
            ),
            "scenario_snapshot": (
                f"figures/{fig_paths['scenario_snapshot']}" if fig_paths.get("scenario_snapshot") else None
            ),
        },
        heatmap_pages=fig_paths.get("heatmap_pages", []),
        heatmap_modes=fig_paths.get("heatmap_modes", []),
        default_heatmap_mode=fig_paths.get("default_heatmap_mode"),
        appendix_tables=appendix_tables,
        show_appendix=bool(cfg.get("output", {}).get("show_appendix", False)),
    )

    out_path = outdir / cfg["output"]["report_filename"]
    out_path.write_text(html, encoding="utf-8")

    payload_path = outdir / "tables" / "dashboard_payload.json"
    payload_path.write_text(json.dumps(dashboard_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    output_cfg = cfg.get("output", {}) or {}
    write_dashboard = bool(output_cfg.get("write_dashboard", True))
    if write_dashboard:
        dashboard_template_name = str(output_cfg.get("dashboard_template", "dashboard_template.html"))
        dashboard_nav = {
            "overview": str(output_cfg.get("dashboard_filename", "dashboard.html")),
            "decision": str(output_cfg.get("dashboard_decision_filename", "dashboard_decision.html")),
        }
        try:
            dashboard_template = env.get_template(dashboard_template_name)
        except Exception:
            dashboard_template = None
        if dashboard_template is not None:
            page_specs = [
                ("overview", dashboard_nav["overview"]),
                ("decision", dashboard_nav["decision"]),
            ]
            kept_files = set()
            for page_key, page_filename in page_specs:
                dashboard_html = dashboard_template.render(
                    meta=meta,
                    overview=overview,
                    decision_card=decision_card_block,
                    dashboard_payload=dashboard_payload,
                    dashboard_page=page_key,
                    dashboard_nav=dashboard_nav,
                )
                (outdir / page_filename).write_text(dashboard_html, encoding="utf-8")
                kept_files.add(page_filename)

            stale_candidates = [
                str(output_cfg.get("dashboard_sensitivity_filename", "dashboard_sensitivity.html")),
                str(output_cfg.get("dashboard_allocation_filename", "dashboard_allocation.html")),
                str(output_cfg.get("dashboard_scenarios_filename", "dashboard_scenarios.html")),
                str(output_cfg.get("dashboard_actions_filename", "dashboard_actions.html")),
            ]
            for stale_name in stale_candidates:
                if stale_name in kept_files:
                    continue
                stale_path = outdir / stale_name
                if stale_path.exists() and stale_path.is_file():
                    stale_path.unlink()

