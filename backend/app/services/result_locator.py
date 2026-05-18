from __future__ import annotations

import json
import csv
from pathlib import Path
from typing import Any

from backend.app.services.paths import PROJECT_ROOT


def _roi_csv_path(output_tag: str) -> Path:
    return (
        PROJECT_ROOT
        / "data"
        / "output"
        / "01_runs"
        / output_tag
        / f"prior_sensitivity_roi_multi_{output_tag}.csv"
    )


def _to_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _fmt_float(value: Any, digits: int = 3) -> str:
    parsed = _to_float(value)
    return "NA" if parsed is None else f"{parsed:.{digits}f}"


def _build_roi_prior_posterior_table_from_csv(output_tag: str) -> dict[str, Any]:
    path = _roi_csv_path(output_tag)
    if not path.exists():
        return {
            "available": False,
            "interval": "50%",
            "has_95": False,
            "rows": [],
            "reason": (
                "Prior-vs-posterior evidence artifacts were not generated for this run. "
                f"Missing data/output/01_runs/{output_tag}/prior_sensitivity_roi_multi_{output_tag}.csv."
            ),
        }

    required = {
        "target_channel",
        "channel",
        "roi_prior_mu",
        "roi_prior_sigma",
        "roi_prior_dist",
        "estimated_roi",
        "posterior_roi_p25",
        "posterior_roi_p75",
        "prior_roi_mu_channel",
    }
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(required - fieldnames)
        if missing:
            return {
                "available": False,
                "interval": "50%",
                "has_95": False,
                "rows": [],
                "reason": (
                    "Prior-vs-posterior evidence artifacts were generated but cannot be plotted. "
                    f"ROI CSV is missing required columns: {', '.join(missing)}."
                ),
            }
        has_95 = {"posterior_roi_p05", "posterior_roi_p95"}.issubset(fieldnames)
        rows = []
        for raw in reader:
            target_channel = str(raw.get("target_channel") or "").strip()
            channel = str(raw.get("channel") or "").strip()
            if not target_channel or channel != target_channel:
                continue
            mean = _to_float(raw.get("estimated_roi"))
            p25 = _to_float(raw.get("posterior_roi_p25"))
            p75 = _to_float(raw.get("posterior_roi_p75"))
            prior_mu = _to_float(raw.get("prior_roi_mu_channel"))
            if mean is None or p25 is None or p75 is None or prior_mu is None:
                continue
            rows.append(
                {
                    "channel": target_channel,
                    "prior_variant": (
                        f"mu={_fmt_float(raw.get('roi_prior_mu'))}, "
                        f"sigma={_fmt_float(raw.get('roi_prior_sigma'))}, "
                        f"dist={str(raw.get('roi_prior_dist') or 'NA').strip()}"
                    ),
                    "prior_roi_mu": prior_mu,
                    "prior_roi_sigma": _to_float(raw.get("roi_prior_sigma")),
                    "posterior_roi_estimate": mean,
                    "posterior_50_lower": p25,
                    "posterior_50_upper": p75,
                    "posterior_95_lower": _to_float(raw.get("posterior_roi_p05")) if has_95 else None,
                    "posterior_95_upper": _to_float(raw.get("posterior_roi_p95")) if has_95 else None,
                }
            )

    if not rows:
        return {
            "available": False,
            "interval": "50%",
            "has_95": has_95,
            "rows": [],
            "reason": (
                "Prior-vs-posterior evidence artifacts were generated, but no plottable "
                "self-response rows were found in the ROI CSV."
            ),
        }

    rows.sort(key=lambda row: (str(row["channel"]), row.get("prior_roi_mu") or 0, row.get("prior_roi_sigma") or 0, str(row["prior_variant"])))
    return {"available": True, "interval": "50%", "has_95": has_95, "rows": rows, "reason": "", "source_csv": str(path)}


def locate_result_artifacts(output_tag: str) -> dict[str, Any]:
    runs_dir = PROJECT_ROOT / "data" / "output" / "01_runs" / output_tag
    tables_dir = PROJECT_ROOT / "data" / "output" / "02_tables" / output_tag
    report_dir = PROJECT_ROOT / "data" / "output" / "03_reports" / "report" / output_tag
    tornado_dir = PROJECT_ROOT / "data" / "output" / "03_reports" / "tornado_outputs" / output_tag
    roi_csv_path = _roi_csv_path(output_tag)
    payload_path = report_dir / "tables" / "dashboard_payload.json"
    report_html_path = report_dir / "dashboard.html"

    artifacts: dict[str, Any] = {
        "output_tag": output_tag,
        "dashboard_payload": str(payload_path) if payload_path.exists() else None,
        "report_html": str(report_html_path) if report_html_path.exists() else None,
        "runs_dir": str(runs_dir) if runs_dir.exists() else None,
        "tables_dir": str(tables_dir) if tables_dir.exists() else None,
        "report_dir": str(report_dir) if report_dir.exists() else None,
        "figures_dir": str(report_dir / "figures") if (report_dir / "figures").exists() else None,
        "tornado_outputs_dir": str(tornado_dir) if tornado_dir.exists() else None,
        "roi_csv": str(roi_csv_path) if roi_csv_path.exists() else None,
    }
    return artifacts


def load_payload_for_run(run_id: str, output_tag: str | None = None) -> dict[str, Any]:
    if not output_tag:
        raise FileNotFoundError(f"No output tag is recorded for run {run_id}.")
    payload = locate_result_artifacts(output_tag).get("dashboard_payload")
    if not payload:
        raise FileNotFoundError(
            f"Results are not available for run {run_id}. Expected dashboard artifact "
            f"data/output/03_reports/report/{output_tag}/tables/dashboard_payload.json was not found."
        )
    with Path(str(payload)).open("r", encoding="utf-8") as f:
        data = json.load(f)

    tables_dir = Path(str(payload)).parent
    diagnostics: dict[str, Any] = dict(data.get("diagnostics") or {})
    diagnostics.setdefault("overview", data.get("diagnostics_overview") or {})
    diagnostics_files = {
        "status_rows": "diagnostics_status_breakdown.csv",
        "primary_rows": "diagnostics_primary_checks.csv",
        "flagged_rows": "diagnostics_flagged_channels.csv",
        "check_rows": "diagnostics_check_matrix.csv",
    }
    for key, filename in diagnostics_files.items():
        if diagnostics.get(key):
            continue
        path = tables_dir / filename
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", newline="") as f:
            diagnostics[key] = list(csv.DictReader(f))
    if diagnostics:
        diagnostics.setdefault("available", bool(diagnostics.get("overview") or diagnostics.get("check_rows")))
        data["diagnostics"] = diagnostics

    table = data.get("roi_prior_posterior_table")
    if not isinstance(table, dict) or not table.get("rows"):
        data["roi_prior_posterior_table"] = _build_roi_prior_posterior_table_from_csv(output_tag)
    data["result_artifacts"] = locate_result_artifacts(output_tag)
    return data
