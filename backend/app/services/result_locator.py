from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.services.paths import PROJECT_ROOT


def demo_payload_path(run_id: str) -> Path:
    if run_id != "demo_32run":
        raise FileNotFoundError(f"Only demo_32run is available in Phase 3; got {run_id!r}.")
    return PROJECT_ROOT / "data" / "output" / "03_reports" / "report" / "demo_32run" / "tables" / "dashboard_payload.json"


def load_demo_payload(run_id: str) -> dict[str, Any]:
    path = demo_payload_path(run_id)
    if not path.exists():
        raise FileNotFoundError(f"Dashboard payload not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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
    if run_id == "demo_32run":
        return load_demo_payload(run_id)
    if not output_tag:
        raise FileNotFoundError(f"No output tag is recorded for run {run_id}.")
    payload = locate_result_artifacts(output_tag).get("dashboard_payload")
    if not payload:
        raise FileNotFoundError(f"Dashboard payload not found for run {run_id}.")
    with Path(str(payload)).open("r", encoding="utf-8") as f:
        return json.load(f)
