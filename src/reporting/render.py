from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.formatting import (
    fmt_money as _fmt_money,
    is_missing_value as _is_missing_value,
    fmt_float_safe as _fmt_float_safe,
    to_float_safe as _to_float_safe,
)


def _clean_text_safe(x, missing_label: str = "-") -> str:
    if _is_missing_value(x):
        return missing_label
    return str(x).strip()


def _truncate_text(s: str, max_len: int = 58) -> str:
    text = str(s)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "..."


def _json_compatible(value, *, float_decimals: int | None = None):
    """Recursively convert payload values to strict-JSON-safe primitives.

    In particular, converts NaN/inf to None so browser-side JSON.parse succeeds.
    """
    if isinstance(value, dict):
        return {str(k): _json_compatible(v, float_decimals=float_decimals) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_compatible(v, float_decimals=float_decimals) for v in value]
    if isinstance(value, tuple):
        return [_json_compatible(v, float_decimals=float_decimals) for v in value]
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        value_f = float(value)
        if isinstance(float_decimals, int) and float_decimals >= 0:
            return round(value_f, float_decimals)
        return value_f
    if isinstance(value, int):
        return int(value)

    # numpy/pandas scalar fallback
    if hasattr(value, "item"):
        try:
            return _json_compatible(value.item(), float_decimals=float_decimals)
        except Exception:
            pass
    return value


def _build_target_channel_detail_payload(metrics: dict, source_files: dict | None = None) -> dict:
    """Build selected target-channel sensitivity slices from existing CSV/report rows."""
    import pandas as pd

    source_files = source_files or {}
    preferred_order = ["google", "meta", "tiktok", "snapchat", "moloco", "liveintent", "beehiiv", "amazon"]

    def _read_csv(path_value):
        if not path_value:
            return pd.DataFrame()
        try:
            path = Path(path_value)
            if path.exists() and path.is_file():
                return pd.read_csv(path)
        except Exception:
            return pd.DataFrame()
        return pd.DataFrame()

    def _ensure_target_col(df):
        if df is None or df.empty:
            return pd.DataFrame()
        out = df.copy()
        if "target_channel" not in out.columns:
            for alt in ["targets", "target_channels", "qc_target_channels"]:
                if alt in out.columns:
                    out["target_channel"] = out[alt]
                    break
        if "target_channel" in out.columns:
            out["target_channel"] = out["target_channel"].astype(str).str.strip().str.lower()
        if "channel" in out.columns:
            out["channel"] = out["channel"].astype(str).str.strip().str.lower()
        return out

    def _status_bucket(value) -> str:
        text = _clean_text_safe(value, "UNKNOWN").upper()
        if "FAIL" in text:
            return "FAIL"
        if "REVIEW" in text or "WARN" in text:
            return "REVIEW"
        if "PASS" in text:
            return "PASS"
        return text or "UNKNOWN"

    def _status_col(df):
        for col in ["qc_status_code", "qc_overall_status", "qc_pass_fail"]:
            if col in df.columns:
                return col
        return None

    def _boolish(value) -> bool:
        if value is None:
            return False
        try:
            if pd.isna(value):
                return False
        except Exception:
            pass
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in {"true", "1", "yes", "y"}

    def _sort_key(channel: str):
        c = str(channel).lower()
        return (preferred_order.index(c) if c in preferred_order else len(preferred_order), c)

    decision_card = metrics.get("decision_card", {}) or {}
    robust_source = metrics.get("robustness_score", {}) or {}
    robust_available = bool(robust_source.get("available")) and _to_float_safe(
        robust_source.get("overall_model_robustness_score")
    ) is not None
    robustness_channel_df = _read_csv(robust_source.get("channel_csv"))
    if not robustness_channel_df.empty and "channel" in robustness_channel_df.columns:
        robustness_channel_df = robustness_channel_df.copy()
        robustness_channel_df["channel"] = robustness_channel_df["channel"].astype(str).str.strip().str.lower()
    else:
        robustness_channel_df = pd.DataFrame()
    robust_subscores = [
        {
            "id": _clean_text_safe(item.get("id"), ""),
            "label": _clean_text_safe(item.get("label"), ""),
            "value": _to_float_safe(item.get("value")),
        }
        for item in (decision_card.get("score_subscores", []) or [])
    ]
    if not robust_subscores:
        robust_subscores = [
            {"id": "prior", "label": "Sensitivity Elasticity", "value": None},
            {"id": "data", "label": "Data Influence", "value": None},
            {"id": "cross", "label": "Cross-Channel", "value": None},
        ]
    robustness_framework = {
        "available": robust_available,
        "score": _to_float_safe(robust_source.get("overall_model_robustness_score")),
        "band": _clean_text_safe(robust_source.get("overall_model_robustness_band"), "Unavailable"),
        "subscores": robust_subscores,
        "note": (
            _clean_text_safe(
                (decision_card.get("score_meta", {}) or {}).get("methodology_note"),
                "",
            )
            or _clean_text_safe(decision_card.get("score_note"), "")
            or "Project-defined prior sensitivity heuristic loaded from the model-level robustness output; higher subscore meters indicate stronger stability."
            if robust_available
            else f"Robustness score unavailable: {_clean_text_safe(robust_source.get('reason'), 'required robustness output missing')}."
        ),
        "scope": "global",
        "source_row": {},
    }

    report_df = _ensure_target_col(metrics.get("merged_df"))
    roi_df = _ensure_target_col(_read_csv(source_files.get("roi_csv")))
    run_df = _ensure_target_col(_read_csv(source_files.get("runs_csv")))
    tornado_df = _ensure_target_col(_read_csv(source_files.get("tornado_csv")))
    if tornado_df.empty:
        tornado_df = report_df.copy()

    channels = set()
    for df in [report_df, roi_df, run_df, tornado_df]:
        if df is not None and not df.empty and "target_channel" in df.columns:
            channels.update([str(v).strip().lower() for v in df["target_channel"].dropna().tolist() if str(v).strip()])
    options = sorted(channels, key=_sort_key)

    summaries = {}
    for target in options:
        roi_target = roi_df.loc[roi_df.get("target_channel", pd.Series(dtype=str)) == target].copy() if not roi_df.empty else pd.DataFrame()
        if not roi_target.empty and "channel" in roi_target.columns:
            self_rows_df = roi_target.loc[roi_target["channel"] == target].copy()
        else:
            self_rows_df = pd.DataFrame()
        if self_rows_df.empty and not report_df.empty:
            fallback = report_df.loc[report_df.get("target_channel", pd.Series(dtype=str)) == target].copy()
            if "channel" in fallback.columns:
                self_rows_df = fallback.loc[fallback["channel"] == target].copy()

        self_rows = []
        for row in self_rows_df.to_dict(orient="records"):
            self_rows.append(
                {
                    "run_id": _clean_text_safe(row.get("run_id"), ""),
                    "target_channel": target,
                    "channel": _clean_text_safe(row.get("channel"), target),
                    "roi_prior_mu": _to_float_safe(row.get("roi_prior_mu")),
                    "roi_prior_sigma": _to_float_safe(row.get("roi_prior_sigma")),
                    "roi_prior_dist": _clean_text_safe(row.get("roi_prior_dist"), _clean_text_safe(row.get("prior_roi_dist_channel"), "")),
                    "estimated_roi": _to_float_safe(row.get("estimated_roi", row.get("roi_new"))),
                    "posterior_roi_p25": _to_float_safe(row.get("posterior_roi_p25", row.get("roi_new_p25"))),
                    "posterior_roi_p75": _to_float_safe(row.get("posterior_roi_p75", row.get("roi_new_p75"))),
                    "posterior_roi_p50": _to_float_safe(row.get("posterior_roi_p50", row.get("roi_new_p50"))),
                    "qc_status_code": _status_bucket(row.get("qc_status_code", row.get("qc_overall_status", row.get("qc_pass_fail")))),
                    "is_baseline": _boolish(row.get("is_baseline", False)),
                }
            )
        self_rows.sort(
            key=lambda r: (
                r["roi_prior_mu"] if r["roi_prior_mu"] is not None else float("inf"),
                r["roi_prior_sigma"] if r["roi_prior_sigma"] is not None else float("inf"),
                r["roi_prior_dist"],
            )
        )

        settings_seen = {
            (
                r.get("roi_prior_mu"),
                r.get("roi_prior_sigma"),
                r.get("roi_prior_dist"),
            )
            for r in self_rows
        }
        posterior_vals = [r["estimated_roi"] for r in self_rows if r.get("estimated_roi") is not None]

        run_target = run_df.loc[run_df.get("target_channel", pd.Series(dtype=str)) == target].copy() if not run_df.empty else pd.DataFrame()
        qc_df = run_target if not run_target.empty else self_rows_df
        qc_col = _status_col(qc_df) if qc_df is not None and not qc_df.empty else None
        qc_mix: dict[str, int] = {}
        if qc_col:
            for status in qc_df[qc_col].map(_status_bucket).tolist():
                qc_mix[status] = qc_mix.get(status, 0) + 1

        system_candidates = []
        for source_rank, (source_name, source_df) in enumerate(
            [
                ("tornado", tornado_df),
                ("report_input", report_df),
                ("roi_csv", roi_df),
            ]
        ):
            if source_df is None or source_df.empty or "channel" not in source_df.columns:
                continue
            target_df = source_df.loc[source_df.get("target_channel", pd.Series(dtype=str)) == target].copy()
            if target_df.empty:
                continue
            outcome_count = int(target_df["channel"].dropna().astype(str).str.lower().nunique())
            has_movement = any(c in target_df.columns for c in ["delta_value_abs", "delta_pct", "delta_abs", "pct_change"])
            system_candidates.append(
                {
                    "name": source_name,
                    "df": target_df,
                    "outcome_count": outcome_count,
                    "has_movement": has_movement,
                    "source_rank": source_rank,
                }
            )
        system_choice = max(
            system_candidates,
            key=lambda item: (
                item["outcome_count"],
                1 if item["has_movement"] else 0,
                -item["source_rank"],
            ),
            default=None,
        )
        system_df = system_choice["df"] if system_choice else pd.DataFrame()
        system_source = system_choice["name"] if system_choice else ""

        signed_candidates = [
            item
            for item in system_candidates
            if item["name"] in {"report_input", "roi_csv"} and item["outcome_count"] > 1
        ]
        signed_choice = max(
            signed_candidates,
            key=lambda item: (item["outcome_count"], len(item["df"]), -item["source_rank"]),
            default=None,
        )
        if signed_choice is not None:
            system_df = signed_choice["df"]
            system_source = f"{signed_choice['name']}_signed_reconstructed"

        posterior_candidates = [
            item
            for item in system_candidates
            if item["name"] in {"report_input", "roi_csv"} and item["outcome_count"] > 1
        ]
        posterior_choice = max(
            posterior_candidates,
            key=lambda item: (item["outcome_count"], len(item["df"]), -item["source_rank"]),
            default=None,
        )
        posterior_df = posterior_choice["df"] if posterior_choice else system_df

        system_rows = []
        for row in system_df.to_dict(orient="records"):
            roi_baseline = _to_float_safe(row.get("roi_baseline", row.get("baseline_roi")))
            roi_new = _to_float_safe(row.get("roi_new", row.get("estimated_roi")))
            signed_delta_pct = None
            if roi_baseline is not None and roi_new is not None and abs(float(roi_baseline)) >= 1e-12:
                signed_delta_pct = ((float(roi_new) / float(roi_baseline)) - 1.0) * 100.0
            delta_abs = _to_float_safe(row.get("delta_abs"))
            delta_value_abs = _to_float_safe(row.get("delta_value_abs"))
            is_baseline = _boolish(row.get("is_baseline", False))
            if is_baseline:
                signed_delta_pct = 0.0
            system_rows.append(
                {
                    "run_id": _clean_text_safe(row.get("run_id"), ""),
                    "target_channel": target,
                    "channel": _clean_text_safe(row.get("channel"), ""),
                    "roi_prior_mu": _to_float_safe(row.get("roi_prior_mu", row.get("roi_mu"))),
                    "roi_prior_sigma": _to_float_safe(row.get("roi_prior_sigma", row.get("roi_sigma"))),
                    "roi_prior_dist": _clean_text_safe(row.get("roi_prior_dist", row.get("roi_dist")), ""),
                    "roi_baseline": roi_baseline,
                    "roi_new": roi_new,
                    "delta_abs": delta_abs,
                    "signed_delta_pct": signed_delta_pct,
                    "delta_value_abs": delta_value_abs,
                    "delta_outcome_abs": _to_float_safe(row.get("delta_outcome_abs")),
                    "qc_status_code": _status_bucket(row.get("qc_status_code", row.get("qc_overall_status", row.get("qc_pass_fail")))),
                    "is_baseline": is_baseline,
                    "movement_value": next(
                        (
                            v
                            for v in [
                                abs(signed_delta_pct) if signed_delta_pct is not None and not is_baseline else None,
                                delta_value_abs if not is_baseline else None,
                                abs(delta_abs) if delta_abs is not None and not is_baseline else None,
                            ]
                            if v is not None
                        ),
                        None,
                    ),
                }
            )

        channel_groups: dict[str, list[dict]] = {}
        for row in system_rows:
            ch = str(row.get("channel") or "").lower()
            if not ch:
                continue
            channel_groups.setdefault(ch, []).append(row)
        impact_rows = []
        for ch, rows in channel_groups.items():
            movement_rows = [r for r in rows if not bool(r.get("is_baseline", False))]
            pct_signed = [r["signed_delta_pct"] for r in movement_rows if r.get("signed_delta_pct") is not None]
            abs_vals = [r["delta_abs"] for r in rows if r.get("delta_abs") is not None]
            if not abs_vals:
                roi_vals = [r["roi_new"] for r in rows if r.get("roi_new") is not None]
                if len(roi_vals) >= 2:
                    abs_vals = [max(roi_vals) - min(roi_vals)]
            value_vals = [r["delta_value_abs"] for r in rows if r.get("delta_value_abs") is not None]
            roi_signed = [r["delta_abs"] for r in rows if r.get("delta_abs") is not None]
            left_pct = min(pct_signed) if pct_signed else None
            right_pct = max(pct_signed) if pct_signed else None
            impact_rows.append(
                {
                    "channel": ch,
                    "is_self_response": ch == target,
                    "response_scope": "Self-response" if ch == target else "Non-self",
                    "min_signed_delta_pct": left_pct,
                    "max_signed_delta_pct": right_pct,
                    "max_abs_delta_pct": max([abs(v) for v in [left_pct, right_pct] if v is not None], default=None),
                    "max_abs_delta_roi": max([abs(v) for v in abs_vals], default=None),
                    "max_abs_delta_value": max(value_vals, default=None),
                    "left_pct": left_pct,
                    "right_pct": right_pct,
                    "left_delta_roi": min(roi_signed) if roi_signed else None,
                    "right_delta_roi": max(roi_signed) if roi_signed else None,
                    "n_rows": len(movement_rows),
                }
            )
        impact_rows.sort(
            key=lambda r: next(
                (v for v in [r.get("max_abs_delta_pct"), r.get("max_abs_delta_value"), r.get("max_abs_delta_roi")] if v is not None),
                -1,
            ),
            reverse=True,
        )
        largest = impact_rows[0] if impact_rows else None
        system_posterior_rows = int(len(posterior_df))
        system_non_baseline_movement_rows = int(sum(1 for r in system_rows if not bool(r.get("is_baseline", False))))
        target_robustness = robustness_framework
        if not robustness_channel_df.empty:
            robust_match = robustness_channel_df.loc[robustness_channel_df["channel"] == target].copy()
            if not robust_match.empty:
                robust_row = robust_match.iloc[-1].to_dict()
                robust_score = _to_float_safe(robust_row.get("overall_channel_robustness_score"))
                robust_band = _clean_text_safe(robust_row.get("robustness_band"), "Unavailable").title()
                source_name = Path(str(robust_source.get("channel_csv", "") or "")).name
                robust_runs = int(_to_float_safe(robust_row.get("n_runs_used")) or 0)
                target_robustness = {
                    "available": robust_score is not None,
                    "score": robust_score,
                    "overall_channel_robustness_score": robust_score,
                    "band": robust_band,
                    "robustness_band": robust_band,
                    "absolute_band": _clean_text_safe(robust_row.get("absolute_band"), robust_band),
                    "band_method": _clean_text_safe(robust_row.get("band_method"), ""),
                    "relative_rank": _to_float_safe(robust_row.get("relative_rank")),
                    "relative_rank_total": _to_float_safe(robust_row.get("relative_rank_total")),
                    "relative_rank_label": _clean_text_safe(robust_row.get("relative_rank_label"), ""),
                    "relative_rank_method": _clean_text_safe(robust_row.get("relative_rank_method"), ""),
                    "subscores": [
                        {
                            "id": "prior",
                            "label": "Sensitivity Elasticity",
                            "value": _to_float_safe(robust_row.get("prior_sensitivity_subscore")),
                        },
                        {
                            "id": "data",
                            "label": "Data Influence",
                            "value": _to_float_safe(robust_row.get("data_influence_subscore")),
                        },
                        {
                            "id": "cross",
                            "label": "Cross-Channel",
                            "value": _to_float_safe(robust_row.get("cross_channel_subscore")),
                        },
                    ],
                    "note": f"src={source_name or 'robustness_channel_<tag>.csv'} | channel={target} | n={robust_runs}",
                    "scope": "target_channel",
                    "source_row": _json_compatible(robust_row, float_decimals=6),
                }

        summaries[target] = {
            "target_channel": target,
            "label": target.upper(),
            "prior_settings_tested": len(settings_seen),
            "self_response_rows": self_rows,
            "posterior_roi_mean_min": min(posterior_vals) if posterior_vals else None,
            "posterior_roi_mean_max": max(posterior_vals) if posterior_vals else None,
            "qc_status_mix": qc_mix,
            "system_response_rows": system_rows,
            "system_impact_rows": impact_rows,
            "system_outcome_channel_count": len(channel_groups),
            "system_posterior_rows": system_posterior_rows,
            "system_non_baseline_movement_rows": system_non_baseline_movement_rows,
            "system_source": system_source,
            "largest_movement": largest,
            "robustness": target_robustness,
        }

    default_channel = options[0] if options else ""
    top_rows = metrics.get("recommendations", []) or []
    return {
        "available": bool(options),
        "options": [{"value": c, "label": c.upper()} for c in options],
        "default_channel": default_channel,
        "recommended_channel": default_channel,
        "recommendation_source": _clean_text_safe(top_rows[0], "") if top_rows else "",
        "summaries": summaries,
        "notes": [
            "Self-response rows require target_channel == selected target and channel == selected target.",
            "Full-system rows use target_channel == selected target and include every modeled outcome channel from each Meridian run.",
        ],
    }


def _build_roi_prior_posterior_table(source_files: dict | None = None) -> dict:
    """Mirror the source rows used by the global ROI prior-vs-posterior plot."""
    import pandas as pd

    source_files = source_files or {}
    path_value = source_files.get("roi_csv")
    if not path_value:
        return {"available": False, "interval": "50%", "has_95": False, "rows": [], "reason": "ROI source CSV not provided."}
    path = Path(path_value)
    if not path.exists() or not path.is_file():
        return {"available": False, "interval": "50%", "has_95": False, "rows": [], "reason": "ROI source CSV not found."}

    try:
        df = pd.read_csv(path)
    except Exception as exc:
        return {"available": False, "interval": "50%", "has_95": False, "rows": [], "reason": f"Failed to read ROI source CSV: {exc}"}

    required = [
        "target_channel",
        "channel",
        "roi_prior_mu",
        "roi_prior_sigma",
        "roi_prior_dist",
        "estimated_roi",
        "posterior_roi_p25",
        "posterior_roi_p75",
        "prior_roi_mu_channel",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {
            "available": False,
            "interval": "50%",
            "has_95": False,
            "rows": [],
            "reason": f"ROI source CSV missing required columns: {', '.join(missing)}",
        }

    df = df[df["channel"].astype(str) == df["target_channel"].astype(str)].copy()
    has_95 = {"posterior_roi_p05", "posterior_roi_p95"}.issubset(df.columns)
    numeric_cols = [
        "roi_prior_mu",
        "roi_prior_sigma",
        "prior_roi_mu_channel",
        "estimated_roi",
        "posterior_roi_p25",
        "posterior_roi_p75",
    ]
    if has_95:
        numeric_cols.extend(["posterior_roi_p05", "posterior_roi_p95"])
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["target_channel", "estimated_roi", "prior_roi_mu_channel", "posterior_roi_p25", "posterior_roi_p75"])
    if df.empty:
        return {"available": False, "interval": "50%", "has_95": has_95, "rows": [], "reason": "No plottable self-response rows found."}

    df = df.sort_values(["target_channel", "roi_prior_mu", "roi_prior_sigma", "roi_prior_dist"])
    rows = []
    for row in df.to_dict(orient="records"):
        rows.append(
            {
                "channel": _clean_text_safe(row.get("target_channel"), ""),
                "prior_variant": (
                    f"mu={_fmt_float_safe(row.get('roi_prior_mu'), digits=3)}, "
                    f"sigma={_fmt_float_safe(row.get('roi_prior_sigma'), digits=3)}, "
                    f"dist={_clean_text_safe(row.get('roi_prior_dist'), 'NA')}"
                ),
                "prior_roi_mu": _to_float_safe(row.get("prior_roi_mu_channel")),
                "prior_roi_sigma": _to_float_safe(row.get("roi_prior_sigma")),
                "posterior_roi_estimate": _to_float_safe(row.get("estimated_roi")),
                "posterior_50_lower": _to_float_safe(row.get("posterior_roi_p25")),
                "posterior_50_upper": _to_float_safe(row.get("posterior_roi_p75")),
                "posterior_95_lower": _to_float_safe(row.get("posterior_roi_p05")) if has_95 else None,
                "posterior_95_upper": _to_float_safe(row.get("posterior_roi_p95")) if has_95 else None,
            }
        )
    return {"available": True, "interval": "50%", "has_95": has_95, "rows": rows, "reason": ""}


def _build_qc_followup_summary(qc_gate: dict) -> dict:
    counts: dict[str, int] = {}
    for row in qc_gate.get("run_rows", []) or []:
        status = _clean_text_safe(row.get("qc_status_code"), "").upper()
        check = _clean_text_safe(row.get("qc_primary_review_check"), "")
        if not check or check == "-" or status == "PASS":
            continue
        counts[check] = counts.get(check, 0) + 1
    if not counts:
        return {
            "available": False,
            "primary_review_check": "",
            "count": 0,
            "reason": "Review reason unavailable in current payload.",
        }
    primary, count = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    return {
        "available": True,
        "primary_review_check": primary,
        "count": count,
        "reason": "",
    }


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


def render_dashboard_output(
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
    output_cfg = cfg.get("output", {}) or {}
    write_report = bool(output_cfg.get("write_report", False))
    report_template_name = "report_template.html"
    report_template_path = template_dir / report_template_name
    template = (
        env.get_template(report_template_name)
        if write_report and report_template_path.exists()
        else None
    )
    if write_report and template is None:
        write_report = False

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
    workbench = metrics.get("workbench", {"available": False})
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
                "tables/qc_gate_summary.csv",
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
    if workbench.get("available"):
        appendix_tables.extend(
            [
                "tables/workbench_run_level.csv",
                "tables/workbench_channel_summary.csv",
                "tables/workbench_mu_marginal_summary.csv",
                "tables/workbench_sigma_marginal_summary.csv",
                "tables/workbench_mu_sigma_split_summary.csv",
                "tables/workbench_mu_sensitivity_rank.csv",
                "tables/workbench_sigma_sensitivity_rank.csv",
            ]
        )
    rank_table_raw_df = metrics["rank_df"].copy()
    rank_table_df = rank_table_raw_df.copy()
    if "baseline_roi" in rank_table_df.columns:
        rank_table_df["baseline_roi"] = rank_table_df["baseline_roi"].map(
            lambda x: "NA" if _to_float_safe(x) is None else f"{float(_to_float_safe(x)):.3f}"
        )
    if "max_abs_pct_change" in rank_table_df.columns:
        rank_table_df["max_abs_pct_change"] = rank_table_df["max_abs_pct_change"].map(
            lambda x: "NA" if _to_float_safe(x) is None else f"{float(_to_float_safe(x)):.3f}%"
        )
    if "max_abs_pct_change_raw" in rank_table_df.columns:
        rank_table_df["max_abs_pct_change_raw"] = rank_table_df["max_abs_pct_change_raw"].map(
            lambda x: "NA" if _to_float_safe(x) is None else f"{float(_to_float_safe(x)):.3f}%"
        )
    if "max_abs_delta_roi" in rank_table_df.columns:
        rank_table_df["max_abs_delta_roi"] = rank_table_df["max_abs_delta_roi"].map(
            lambda x: "NA" if _to_float_safe(x) is None else f"{float(_to_float_safe(x)):.3f}"
        )

    if "primary_metric" in rank_table_df.columns:
        rank_table_df["ranking_metric"] = rank_table_df["primary_metric"].map(
            lambda m: "Max |% Change|" if str(m) == "pct_change" else "Max |Delta ROI|"
        )
        rank_table_df["max_change_display"] = rank_table_df.apply(
            lambda r: (
                "NA"
                if _to_float_safe(r.get("primary_value")) is None
                else (
                    f"{float(_to_float_safe(r.get('primary_value'))):.3f}%"
                    if str(r.get("primary_metric")) == "pct_change"
                    else f"{float(_to_float_safe(r.get('primary_value'))):.3f}"
                )
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
        if "max_abs_pct_change_raw" in unstable_rank_df.columns:
            unstable_rank_df["max_abs_pct_change"] = unstable_rank_df["max_abs_pct_change_raw"]
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
                else f"{float(row.get('qc_baseline_neg_prob')):.3f}"
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
                    "roi_prior_mu": _fmt_float_safe(row.get("roi_prior_mu"), digits=3),
                    "roi_prior_sigma": _fmt_float_safe(row.get("roi_prior_sigma"), digits=3),
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
                        else f"{float(row.get('max_change')):.3f}"
                    ),
                    "median_change": (
                        "NA"
                        if row.get("median_change") is None
                        else _fmt_money(float(row.get("median_change")))
                        if qc_gate.get("rank_metric") == "delta_value_abs"
                        else f"{float(row.get('median_change')):.3f}"
                    ),
                    "n": int(row.get("n", 0) or 0),
                }
            )

        qc_gate_block = {
            "available": True,
            "result": qc_gate.get("result", "REVIEW"),
            "gate_mode": qc_gate.get("gate_mode"),
            "gate_mode_requested": qc_gate.get("gate_mode_requested"),
            "gate_matched_count": qc_gate.get("gate_matched_count"),
            "gate_missing_count": qc_gate.get("gate_missing_count"),
            "gate_warning": qc_gate.get("gate_warning"),
            "mu_values": [_fmt_float_safe(v, digits=3, missing_label="NA") for v in qc_gate.get("mu_values", [])],
            "sigma_values": [_fmt_float_safe(v, digits=3, missing_label="NA") for v in qc_gate.get("sigma_values", [])],
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
            "score_numeric": _to_float_safe(decision_card.get("score_numeric")),
            "score_band": _clean_text_safe(decision_card.get("score_band"), ""),
            "score_note": _clean_text_safe(decision_card.get("score_note"), ""),
            "score_subscores": [
                {
                    "id": _clean_text_safe(x.get("id"), ""),
                    "label": _clean_text_safe(x.get("label"), ""),
                    "value": _to_float_safe(x.get("value")),
                }
                for x in (decision_card.get("score_subscores", []) or [])
            ],
            "policy_name": _clean_text_safe(decision_card.get("policy_name"), ""),
            "policy_rules": decision_card.get("policy_rules", []),
            "triggered_rules": decision_card.get("triggered_rules", []),
            "reasons": decision_card.get("reasons", []),
            "actions": decision_card.get("actions", []),
            "score_meta": {
                "higher_is_better": bool((decision_card.get("score_meta", {}) or {}).get("higher_is_better", True)),
                "overall_weighting": _clean_text_safe((decision_card.get("score_meta", {}) or {}).get("overall_weighting"), ""),
                "band_low_cutoff_q33": _to_float_safe((decision_card.get("score_meta", {}) or {}).get("band_low_cutoff_q33")),
                "band_high_cutoff_q67": _to_float_safe((decision_card.get("score_meta", {}) or {}).get("band_high_cutoff_q67")),
                "band_method": _clean_text_safe((decision_card.get("score_meta", {}) or {}).get("band_method"), ""),
                "absolute_band_method": _clean_text_safe((decision_card.get("score_meta", {}) or {}).get("absolute_band_method"), ""),
                "relative_rank_method": _clean_text_safe((decision_card.get("score_meta", {}) or {}).get("relative_rank_method"), ""),
                "subscore_weights": (decision_card.get("score_meta", {}) or {}).get("subscore_weights", {}) or {},
                "methodology_note": _clean_text_safe((decision_card.get("score_meta", {}) or {}).get("methodology_note"), ""),
                "worst_channel": (decision_card.get("score_meta", {}) or {}).get("worst_channel"),
                "top_sensitive_channels": (decision_card.get("score_meta", {}) or {}).get("top_sensitive_channels", []),
            },
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
                            else f"{float(row.get('spend_share_pct')):.3f}%"
                        ),
                        "effect_share_pct": (
                            "NA"
                            if row.get("effect_share_pct") is None
                            else f"{float(row.get('effect_share_pct')):.3f}%"
                        ),
                        "share_gap_pp": (
                            "NA"
                            if row.get("share_gap_pp") is None
                            else f"{float(row.get('share_gap_pp')):+.3f} pp"
                        ),
                        "estimated_roi": (
                            "NA"
                            if row.get("estimated_roi") is None
                            else f"{float(row.get('estimated_roi')):.3f}"
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
                snap_df["pct_change"] = snap_df["pct_change"].map(
                    lambda x: "NA" if _to_float_safe(x) is None else f"{float(_to_float_safe(x)):.3f}%"
                )
            if "delta_value_used" in snap_df.columns:
                snap_df["delta_value_used"] = snap_df["delta_value_used"].map(
                    lambda x: _fmt_money(float(x)) if str(x).strip().lower() not in {"nan", "none", ""} else "NA"
                )
            if "estimated_roi" in snap_df.columns:
                snap_df["estimated_roi"] = snap_df["estimated_roi"].map(
                    lambda x: "NA" if _to_float_safe(x) is None else f"{float(_to_float_safe(x)):.3f}"
                )
            if "baseline_roi" in snap_df.columns:
                snap_df["baseline_roi"] = snap_df["baseline_roi"].map(
                    lambda x: "NA" if _to_float_safe(x) is None else f"{float(_to_float_safe(x)):.3f}"
                )

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
                    "immediate_share": ("NA" if row.get("immediate_share") is None else f"{100.0*float(row.get('immediate_share')):.3f}%"),
                    "carryover_share": ("NA" if row.get("carryover_share") is None else f"{100.0*float(row.get('carryover_share')):.3f}%"),
                    "avg_lag": ("NA" if row.get("avg_lag") is None else f"{float(row.get('avg_lag')):.3f}"),
                    "half_life_lag": ("NA" if row.get("half_life_lag") is None else f"{float(row.get('half_life_lag')):.3f}"),
                    "n_runs": int(row.get("n_runs", 0) or 0),
                }
            )

        run_rows = []
        for row in structural.get("run_rows", []):
            run_rows.append(
                {
                    "run_id": row.get("run_id"),
                    "roi_prior_mu": ("NA" if row.get("roi_prior_mu") is None else f"{float(row.get('roi_prior_mu')):.3f}"),
                    "roi_prior_sigma": ("NA" if row.get("roi_prior_sigma") is None else f"{float(row.get('roi_prior_sigma')):.3f}"),
                    "roi_prior_dist": row.get("roi_prior_dist"),
                    "adstock_alpha_m": ("NA" if row.get("adstock_alpha_m") is None else f"{float(row.get('adstock_alpha_m')):.3f}"),
                    "saturation_ec_m": ("NA" if row.get("saturation_ec_m") is None else f"{float(row.get('saturation_ec_m')):.3f}"),
                    "saturation_slope_m": ("NA" if row.get("saturation_slope_m") is None else f"{float(row.get('saturation_slope_m')):.3f}"),
                    "max_lag": ("NA" if row.get("max_lag") is None else str(int(float(row.get("max_lag"))))),
                    "adstock_decay_spec": row.get("adstock_decay_spec"),
                    "qc_status_code": row.get("qc_status_code"),
                    "is_baseline": bool(row.get("is_baseline", False)),
                    "total_abs_pct_change": ("NA" if row.get("total_abs_pct_change") is None else f"{float(row.get('total_abs_pct_change')):.3f}"),
                }
            )

        response_rows = []
        for row in structural.get("response_rows", []):
            response_rows.append(
                {
                    "run_id": row.get("run_id"),
                    "channel": row.get("channel"),
                    "target_channel": row.get("target_channel"),
                    "analysis_stage": row.get("analysis_stage"),
                    "struct_profile_id": row.get("struct_profile_id"),
                    "roi_prior_mu": _to_float_safe(row.get("roi_prior_mu")),
                    "roi_prior_sigma": _to_float_safe(row.get("roi_prior_sigma")),
                    "roi_prior_dist": row.get("roi_prior_dist"),
                    "estimated_roi": _to_float_safe(row.get("estimated_roi")),
                    "baseline_roi": _to_float_safe(row.get("baseline_roi")),
                    "pct_change": _to_float_safe(row.get("pct_change")),
                    "abs_pct_change": _to_float_safe(row.get("abs_pct_change")),
                    "contribution_value": _to_float_safe(row.get("contribution_value")),
                    "contribution_share": _to_float_safe(row.get("contribution_share")),
                    "effect_value": _to_float_safe(row.get("effect_value")),
                    "effect_share": _to_float_safe(row.get("effect_share")),
                    "channel_total_spend": _to_float_safe(row.get("channel_total_spend")),
                    "spend_share": _to_float_safe(row.get("spend_share")),
                    "adstock_alpha_m": _to_float_safe(row.get("adstock_alpha_m")),
                    "saturation_ec_m": _to_float_safe(row.get("saturation_ec_m")),
                    "saturation_slope_m": _to_float_safe(row.get("saturation_slope_m")),
                    "max_lag": _to_float_safe(row.get("max_lag")),
                    "adstock_decay_spec": row.get("adstock_decay_spec"),
                    "qc_status_code": row.get("qc_status_code"),
                    "qc_summary_short": row.get("qc_summary_short"),
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
            "response_rows": response_rows,
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
        raw_pct_value = _to_float_safe(row.get("max_abs_pct_change_raw"))
        if primary_value is None and primary_metric == "pct_change":
            primary_value = raw_pct_value
        rank_dashboard_rows.append(
            {
                "channel": _clean_text_safe(row.get("channel"), "unknown"),
                "roi_prior_dist": _clean_text_safe(row.get("roi_prior_dist"), "Unknown"),
                "baseline_roi": _to_float_safe(row.get("baseline_roi")),
                "max_abs_pct_change": _to_float_safe(row.get("max_abs_pct_change")),
                "max_abs_pct_change_raw": raw_pct_value,
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

    workbench_block = {"available": False}
    if workbench.get("available"):
        dist_cfg = workbench.get("dist_config", {}) or {}

        run_rows = []
        run_df = workbench.get("run_level_df")
        if run_df is not None and not run_df.empty:
            for row in run_df.to_dict(orient="records"):
                run_rows.append(
                    {
                        "run_id": _clean_text_safe(row.get("run_id"), ""),
                        "channel": _clean_text_safe(row.get("channel"), "unknown"),
                        "target_channel": _clean_text_safe(row.get("target_channel"), ""),
                        "targets": _clean_text_safe(row.get("targets"), ""),
                        "roi_prior_mu": _to_float_safe(row.get("roi_prior_mu")),
                        "roi_prior_sigma": _to_float_safe(row.get("roi_prior_sigma")),
                        "roi_prior_dist": _clean_text_safe(row.get("roi_prior_dist"), ""),
                        "is_baseline": bool(row.get("is_baseline", False)),
                        "estimated_roi": _to_float_safe(row.get("estimated_roi")),
                        "baseline_roi": _to_float_safe(row.get("baseline_roi")),
                        "pct_change": _to_float_safe(row.get("pct_change")),
                        "delta_abs": _to_float_safe(row.get("delta_abs")),
                        "delta_pct": _to_float_safe(row.get("delta_pct")),
                        "contribution_value": _to_float_safe(row.get("contribution_value")),
                        "contribution_delta": _to_float_safe(row.get("contribution_delta")),
                        "contribution_share": _to_float_safe(row.get("contribution_share")),
                        "effect_value": _to_float_safe(row.get("effect_value")),
                        "effect_share": _to_float_safe(row.get("effect_share")),
                        "channel_total_spend": _to_float_safe(row.get("channel_total_spend")),
                        "spend_share": _to_float_safe(row.get("spend_share")),
                        "adstock_alpha_m": _to_float_safe(row.get("adstock_alpha_m")),
                        "saturation_ec_m": _to_float_safe(row.get("saturation_ec_m")),
                        "saturation_slope_m": _to_float_safe(row.get("saturation_slope_m")),
                        "max_lag": _to_float_safe(row.get("max_lag")),
                        "adstock_decay_spec": _clean_text_safe(row.get("adstock_decay_spec"), ""),
                        "qc_status_code": _clean_text_safe(row.get("qc_status_code"), ""),
                        "qc_summary_short": _clean_text_safe(row.get("qc_summary_short"), ""),
                        "qc_primary_review_check": _clean_text_safe(row.get("qc_primary_review_check"), ""),
                        "qc_flagged_channels": _clean_text_safe(row.get("qc_flagged_channels"), ""),
                        "qc_review_reason": _clean_text_safe(row.get("qc_review_reason"), ""),
                    }
                )

        def _df_to_records(df_obj):
            if df_obj is None or df_obj.empty:
                return []
            out_rows = []
            for row in df_obj.to_dict(orient="records"):
                out = {}
                for k, v in row.items():
                    if isinstance(v, bool):
                        out[k] = bool(v)
                        continue
                    f = _to_float_safe(v)
                    if f is not None:
                        out[k] = f
                    else:
                        if isinstance(v, str):
                            out[k] = _clean_text_safe(v, "")
                        elif isinstance(v, (int, float)):
                            try:
                                vv = float(v)
                                out[k] = vv if math.isfinite(vv) else None
                            except Exception:
                                out[k] = None
                        else:
                            out[k] = None if _is_missing_value(v) else v
                out_rows.append(out)
            return out_rows

        workbench_block = {
            "available": True,
            "notes": _clean_text_safe(workbench.get("notes"), ""),
            "contribution_col": _clean_text_safe(workbench.get("contribution_col"), ""),
            "contribution_delta_col": _clean_text_safe(workbench.get("contribution_delta_col"), ""),
            "default_channel": _clean_text_safe(workbench.get("default_channel"), ""),
            "available_channels": workbench.get("available_channels", []),
            "mu_values": [float(v) for v in workbench.get("mu_values", [])],
            "sigma_values": [float(v) for v in workbench.get("sigma_values", [])],
            "explicit_baseline": workbench.get("explicit_baseline") or None,
            "dist_config": {
                "primary_dist": _clean_text_safe(dist_cfg.get("primary_dist"), ""),
                "primary_dist_requested": _clean_text_safe(dist_cfg.get("primary_dist_requested"), ""),
                "primary_dist_fallback_used": bool(dist_cfg.get("primary_dist_fallback_used", False)),
                "allow_legacy_distribution_debug": bool(dist_cfg.get("allow_legacy_distribution_debug", False)),
                "available_dists": dist_cfg.get("available_dists", []),
            },
            "run_rows": run_rows,
            "channel_summary_rows": _df_to_records(workbench.get("channel_summary_df")),
            "mu_marginal_rows": _df_to_records(workbench.get("mu_marginal_df")),
            "sigma_marginal_rows": _df_to_records(workbench.get("sigma_marginal_df")),
            "mu_sigma_split_rows": _df_to_records(workbench.get("sensitivity_split_df")),
            "mu_rank_rows": _df_to_records(workbench.get("mu_rank_df")),
            "sigma_rank_rows": _df_to_records(workbench.get("sigma_rank_df")),
        }

    import numpy as _np
    import pandas as _pd
    merged_df_for_tornado = metrics.get("overview_df")
    if merged_df_for_tornado is None or merged_df_for_tornado.empty:
        merged_df_for_tornado = metrics.get("merged_df")
    if merged_df_for_tornado is not None and not merged_df_for_tornado.empty and "is_baseline" in merged_df_for_tornado.columns:
        baseline_mask = merged_df_for_tornado["is_baseline"].astype(str).str.lower().isin({"true", "1", "yes"})
        non_baseline_mask = ~baseline_mask
        non_baseline_rows = merged_df_for_tornado.loc[non_baseline_mask].copy()
        if not non_baseline_rows.empty:
            merged_df_for_tornado = non_baseline_rows
    roi_tornado_rows: list[dict] = []
    if merged_df_for_tornado is not None and not merged_df_for_tornado.empty:
        tornado_range_mode = str(cfg.get("figures", {}).get("tornado_range_mode", "p05p95")).strip().lower()
        for channel, g in merged_df_for_tornado.groupby("channel", as_index=False):
            vals = _np.array([])
            source = ""
            if "pct_change" in g.columns:
                vals = g["pct_change"].dropna().to_numpy(dtype=float)
                source = "pct_change"
            if vals.size == 0 and "pct_change_raw" in g.columns:
                vals = g["pct_change_raw"].dropna().to_numpy(dtype=float)
                source = "pct_change_raw"
            if vals.size == 0:
                continue
            if tornado_range_mode == "minmax":
                left_v = float(_np.min(vals))
                right_v = float(_np.max(vals))
            else:
                left_v = float(_np.quantile(vals, 0.05))
                right_v = float(_np.quantile(vals, 0.95))
            roi_tornado_rows.append({
                "channel": str(channel),
                "left": left_v,
                "right": right_v,
                "impact": max(abs(left_v), abs(right_v)),
                "n": int(vals.size),
                "source": source,
                "unit": "pct",
            })
        roi_tornado_rows.sort(key=lambda r: r["impact"], reverse=True)

    contribution_tornado_rows: list[dict] = []
    tornado_primary_metric = "roi_pct"
    tornado_primary_label = "ROI Change (%)"
    active_kpi_type = ""
    active_revenue_conversion_available = False
    outcome_context = {
        "metric_label": "ROI",
        "kpi_type": "",
        "kpi_type_effective": "",
        "revenue_per_kpi": None,
    }
    if merged_df_for_tornado is not None and not merged_df_for_tornado.empty:
        def _dominant_text_value(columns: list[str]) -> str:
            values: list[str] = []
            for col in columns:
                if col not in merged_df_for_tornado.columns:
                    continue
                values.extend(
                    merged_df_for_tornado[col]
                    .dropna()
                    .astype(str)
                    .str.strip()
                    .str.lower()
                    .replace({"": _np.nan, "nan": _np.nan, "none": _np.nan, "null": _np.nan})
                    .dropna()
                    .tolist()
                )
            return max(set(values), key=values.count) if values else ""

        def _has_positive_number(columns: list[str]) -> bool:
            for col in columns:
                if col not in merged_df_for_tornado.columns:
                    continue
                vals = _pd.to_numeric(merged_df_for_tornado[col], errors="coerce").dropna()
                if bool((vals > 0).any()):
                    return True
            return False

        def _cfg_has_revenue_conversion() -> bool:
            outcome_cfg = cfg.get("outcome", {}) or {}
            single = _to_float_safe(outcome_cfg.get("revenue_per_kpi"))
            if single is not None and single > 0:
                return True
            values = outcome_cfg.get("revenue_per_kpi_values")
            if isinstance(values, (list, tuple)):
                return any((_to_float_safe(v) is not None and float(_to_float_safe(v)) > 0) for v in values)
            value = _to_float_safe(values)
            return value is not None and value > 0

        active_kpi_type = _dominant_text_value(["kpi_type_effective", "kpi_type"])
        configured_kpi_type = str((cfg.get("outcome", {}) or {}).get("kpi_type", "") or "").strip().lower()
        source_kpi_type = _dominant_text_value(["kpi_type"]) or configured_kpi_type
        effective_kpi_type = _dominant_text_value(["kpi_type_effective"]) or active_kpi_type or configured_kpi_type
        active_kpi_type = active_kpi_type or configured_kpi_type
        active_revenue_conversion_available = _has_positive_number(["revenue_per_kpi"]) or _cfg_has_revenue_conversion()
        revenue_per_kpi_value = None
        if "revenue_per_kpi" in merged_df_for_tornado.columns:
            revenue_vals = _pd.to_numeric(merged_df_for_tornado["revenue_per_kpi"], errors="coerce").dropna()
            revenue_vals = revenue_vals[revenue_vals > 0]
            if not revenue_vals.empty:
                revenue_per_kpi_value = float(revenue_vals.iloc[0])
        if revenue_per_kpi_value is None:
            outcome_cfg = cfg.get("outcome", {}) or {}
            single_value = _to_float_safe(outcome_cfg.get("revenue_per_kpi"))
            if single_value is not None and single_value > 0:
                revenue_per_kpi_value = float(single_value)
        outcome_context = {
            "metric_label": "Revenue-equivalent ROI" if revenue_per_kpi_value is not None else "ROI",
            "kpi_type": source_kpi_type,
            "kpi_type_effective": effective_kpi_type,
            "revenue_per_kpi": revenue_per_kpi_value,
        }

        value_source = None
        baseline_values = new_values = None
        if {"incremental_value_baseline", "incremental_value_new"}.issubset(merged_df_for_tornado.columns):
            baseline_values = merged_df_for_tornado["incremental_value_baseline"]
            new_values = merged_df_for_tornado["incremental_value_new"]
            value_source = "incremental_value"
        elif {"incremental_outcome_baseline", "incremental_outcome_new"}.issubset(merged_df_for_tornado.columns):
            baseline_values = merged_df_for_tornado["incremental_outcome_baseline"]
            new_values = merged_df_for_tornado["incremental_outcome_new"]
            value_source = "incremental_outcome"

        if baseline_values is not None and new_values is not None:
            work = merged_df_for_tornado.copy()
            work["_contribution_base_value"] = _pd.to_numeric(baseline_values, errors="coerce")
            work["_contribution_new_value"] = _pd.to_numeric(new_values, errors="coerce")
            if "run_id" in work.columns:
                run_groups = work.groupby("run_id", dropna=False)
                work["_contribution_base_sum"] = run_groups["_contribution_base_value"].transform("sum")
                work["_contribution_new_sum"] = run_groups["_contribution_new_value"].transform("sum")
            else:
                work["_contribution_base_sum"] = work["_contribution_base_value"].sum()
                work["_contribution_new_sum"] = work["_contribution_new_value"].sum()
            base_valid = work["_contribution_base_sum"].abs() >= 1e-9
            new_valid = work["_contribution_new_sum"].abs() >= 1e-9
            work["_contribution_base_share"] = _np.where(
                base_valid,
                work["_contribution_base_value"] / work["_contribution_base_sum"],
                _np.nan,
            )
            work["_contribution_new_share"] = _np.where(
                new_valid,
                work["_contribution_new_value"] / work["_contribution_new_sum"],
                _np.nan,
            )
            work["_contribution_share_delta_pp"] = 100.0 * (
                work["_contribution_new_share"] - work["_contribution_base_share"]
            )
            tornado_range_mode = str(cfg.get("figures", {}).get("tornado_range_mode", "p05p95")).strip().lower()
            for channel, g in work.groupby("channel", as_index=False):
                vals = g["_contribution_share_delta_pp"].dropna().to_numpy(dtype=float)
                if vals.size == 0:
                    continue
                if tornado_range_mode == "minmax":
                    left_v = float(_np.min(vals))
                    right_v = float(_np.max(vals))
                else:
                    left_v = float(_np.quantile(vals, 0.05))
                    right_v = float(_np.quantile(vals, 0.95))
                contribution_tornado_rows.append({
                    "channel": str(channel),
                    "left": left_v,
                    "right": right_v,
                    "impact": max(abs(left_v), abs(right_v)),
                    "n": int(vals.size),
                    "source": f"{value_source}_share",
                    "unit": "pp",
                })
            contribution_tornado_rows.sort(key=lambda r: r["impact"], reverse=True)

    use_contribution_tornado = active_kpi_type == "non_revenue" and not active_revenue_conversion_available and bool(contribution_tornado_rows)
    if use_contribution_tornado:
        tornado_primary_metric = "contribution_pct"
        tornado_primary_label = "Contribution Share Change (pp)"

    dollar_tornado_rows: list[dict] = []
    dollar_reason = str(dollar.get("reason", "") or "")
    dollar_source = str(dollar.get("source", "") or "")
    dps_note = str(dollar.get("dollars_per_subscription_note", "unknown"))
    dps_value = _to_float_safe(dps_note)
    default_subscription_dollars = dps_value is not None and abs(float(dps_value) - 100.0) <= 1e-9
    dollar_values_meaningful = bool(dollar.get("available"))
    if use_contribution_tornado and not active_revenue_conversion_available:
        dollar_values_meaningful = False
        dollar_reason = (
            "Dollar impact hidden because this non-revenue KPI does not have a revenue-equivalent conversion."
        )
    elif default_subscription_dollars and not active_revenue_conversion_available:
        dollar_values_meaningful = False
        dollar_reason = (
            "Dollar impact hidden because dollars_per_subscription=100 is the default assumption, "
            "not a reliable revenue conversion."
        )

    if dollar_values_meaningful and dollar.get("rank_df") is not None:
        for row in dollar["rank_df"].to_dict(orient="records"):
            left_v = _to_float_safe(row.get("left_dollar"))
            right_v = _to_float_safe(row.get("right_dollar"))
            if left_v is None or right_v is None:
                continue
            dollar_tornado_rows.append({
                "channel": str(row.get("channel", "")),
                "left_dollar": float(left_v),
                "right_dollar": float(right_v),
                "max_abs_dollar_change": float(max(abs(left_v), abs(right_v))),
                "median_dollar_change": _to_float_safe(row.get("median_dollar_change")),
                "n": int(row.get("n", 0) or 0),
            })

    meridian_official_dir = outdir / "figures" / "meridian_official"
    manifest_data = {}
    manifest_path = meridian_official_dir / "manifest.json"
    if manifest_path.exists() and manifest_path.is_file():
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except Exception:
            manifest_data = {}
    if not isinstance(manifest_data, dict):
        manifest_data = {}

    def _official_rel(filename: str) -> str | None:
        p = meridian_official_dir / filename
        if p.exists() and p.is_file():
            return f"figures/meridian_official/{filename}"
        return None

    official_chart_keys = [
        "spend_vs_contribution",
        "roi_by_channel",
        "roi_vs_mroi",
        "roi_vs_effectiveness",
        "contribution_waterfall",
        "contribution_over_time",
    ]
    official_chart_defaults = {
        "spend_vs_contribution": "spend_vs_contribution.html",
        "roi_by_channel": "roi_by_channel.html",
        "roi_vs_mroi": "roi_vs_mroi.html",
        "roi_vs_effectiveness": "roi_vs_effectiveness.html",
        "contribution_waterfall": "contribution_waterfall.html",
        "contribution_over_time": "contribution_over_time.html",
    }
    manifest_files_raw = manifest_data.get("files", {}) if isinstance(manifest_data, dict) else {}
    manifest_files = manifest_files_raw if isinstance(manifest_files_raw, dict) else {}
    meridian_official_files = {
        key: _official_rel(str(manifest_files.get(key) or official_chart_defaults[key]))
        for key in official_chart_keys
    }

    manifest_specs_raw = manifest_data.get("chart_specs", {}) if isinstance(manifest_data, dict) else {}
    meridian_chart_specs = manifest_specs_raw if isinstance(manifest_specs_raw, dict) else {}

    def _extract_vega_spec_from_html(path: Path) -> dict | None:
        try:
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
        except Exception:
            return None
        m = re.search(r"var\s+spec\s*=\s*(\{.*?\})\s*;\s*var\s+embedOpt", text, flags=re.S)
        if not m:
            return None
        try:
            spec = json.loads(m.group(1))
        except Exception:
            return None
        return spec if isinstance(spec, dict) else None

    for key in official_chart_keys:
        if isinstance(meridian_chart_specs.get(key), dict):
            continue
        filename = str(manifest_files.get(key) or official_chart_defaults[key])
        src_path = meridian_official_dir / filename
        if src_path.exists() and src_path.is_file():
            extracted = _extract_vega_spec_from_html(src_path)
            if extracted:
                meridian_chart_specs[key] = extracted

    meridian_official_available = any(isinstance(meridian_chart_specs.get(key), dict) for key in official_chart_keys)

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
            "ranking_rows_total": int(overview.get("ranking_rows_total", 0) or 0),
            "ranking_rows_total_full_system": int(overview.get("ranking_rows_total_full_system", 0) or 0),
            "ranking_rows_used": int(overview.get("ranking_rows_used", 0) or 0),
            "overview_response_scope": str(overview.get("overview_response_scope", "") or ""),
            "overview_response_scope_fallback": bool(overview.get("overview_response_scope_fallback", False)),
            "overview_self_response_rows": int(overview.get("overview_self_response_rows", 0) or 0),
        },
        "outcome_context": outcome_context,
        "thresholds": cfg.get("thresholds", {}),
        "decision_card": decision_card_block,
        "diagnostics": diagnostics,
        "diagnostics_overview": diagnostics.get("overview", {}),
        "rank_rows": rank_dashboard_rows,
        "spend_effect_rows": spend_effect_dashboard_rows,
        "scenario_items": scenario_dashboard_items,
        "roi_tornado_rows": roi_tornado_rows,
        "contribution_tornado_rows": contribution_tornado_rows,
        "tornado_primary_metric": tornado_primary_metric,
        "tornado_primary_label": tornado_primary_label,
        "dollar_tornado_rows": dollar_tornado_rows,
        "dollar_meta": {
            "available": bool(dollar_values_meaningful and dollar_tornado_rows),
            "dollars_per_subscription_note": dps_note,
            "range_mode": str(dollar.get("range_mode", "p05p95")),
            "source": dollar_source,
            "reason": dollar_reason,
        },
        "structural": structural_block,
        "workbench": workbench_block,
        "target_channel_detail": _build_target_channel_detail_payload(metrics, source_files),
        "qc_followup": _build_qc_followup_summary(qc_gate),
        "meridian_official": {
            "available": bool(meridian_official_available),
            "files": meridian_official_files,
            "chart_specs": meridian_chart_specs,
            "manifest": manifest_data,
        },
        "figures": {
            "roi_prior_vs_posterior": (
                f"figures/{fig_paths.get('roi_prior_vs_posterior')}"
                if fig_paths.get("roi_prior_vs_posterior")
                else None
            ),
        },
        "roi_prior_posterior_table": _build_roi_prior_posterior_table(source_files),
        "quick_overview_lines": metrics.get("quick_overview_lines", []),
        "recommendations": metrics.get("recommendations", []),
        "how_this_was_run": metrics.get("how_this_was_run", {"available": False}),
    }
    dashboard_payload = _json_compatible(dashboard_payload, float_decimals=3)
    if write_report and template is not None:
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
            show_appendix=bool(output_cfg.get("show_appendix", False)),
        )

        out_path = outdir / str(output_cfg.get("report_filename", "report.html"))
        out_path.write_text(html, encoding="utf-8")
    elif not write_report:
        stale_report_path = outdir / str(output_cfg.get("report_filename", "report.html"))
        if stale_report_path.exists() and stale_report_path.is_file():
            try:
                stale_report_path.unlink()
            except Exception:
                pass

    payload_path = outdir / "tables" / "dashboard_payload.json"
    payload_path.write_text(
        json.dumps(dashboard_payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )

    write_dashboard = bool(output_cfg.get("write_dashboard", True))
    if write_dashboard:
        dashboard_template_name = str(output_cfg.get("dashboard_template", "dashboard_template.html"))
        dashboard_css_name = str(output_cfg.get("dashboard_css", "dashboard.css"))
        dashboard_css_src = template_dir / dashboard_css_name
        dashboard_css_href = dashboard_css_name
        if dashboard_css_src.exists() and dashboard_css_src.is_file():
            dashboard_css_dest = outdir / dashboard_css_name
            dashboard_css_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(dashboard_css_src, dashboard_css_dest)
        dashboard_nav = {
            "overview": str(output_cfg.get("dashboard_filename", "dashboard.html")),
        }
        try:
            dashboard_template = env.get_template(dashboard_template_name)
        except Exception:
            dashboard_template = None
        if dashboard_template is not None:
            page_specs = [("overview", dashboard_nav["overview"])]
            kept_files = set()
            for page_key, page_filename in page_specs:
                dashboard_html = dashboard_template.render(
                    meta=meta,
                    overview=overview,
                    decision_card=decision_card_block,
                    dashboard_payload=dashboard_payload,
                    dashboard_page=page_key,
                    dashboard_nav=dashboard_nav,
                    dashboard_css_href=dashboard_css_href,
                )
                (outdir / page_filename).write_text(dashboard_html, encoding="utf-8")
                kept_files.add(page_filename)

# Backward-compatible alias for older imports.
render_html_report = render_dashboard_output
