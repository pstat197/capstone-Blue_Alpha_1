from __future__ import annotations

import json
import csv
from pathlib import Path
from typing import Any

from backend.app.services.paths import PROJECT_ROOT


def locate_result_artifacts(output_tag: str) -> dict[str, Any]:
    runs_dir = PROJECT_ROOT / "data" / "output" / "01_runs" / output_tag
    tables_dir = PROJECT_ROOT / "data" / "output" / "02_tables" / output_tag
    report_dir = PROJECT_ROOT / "data" / "output" / "03_reports" / "report" / output_tag
    tornado_dir = PROJECT_ROOT / "data" / "output" / "03_reports" / "tornado_outputs" / output_tag
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
    return data
