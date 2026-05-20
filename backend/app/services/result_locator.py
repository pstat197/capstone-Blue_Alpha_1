from __future__ import annotations

import json
import csv
import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.services.paths import PROJECT_ROOT

REPORTS_ROOT = PROJECT_ROOT / "data" / "output" / "03_reports"


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
    roi_csv_path = _roi_csv_path(output_tag)
    payload_path = report_dir / "tables" / "dashboard_payload.json"

    artifacts: dict[str, Any] = {
        "output_tag": output_tag,
        "dashboard_payload": str(payload_path) if payload_path.exists() else None,
        "payload_path": str(payload_path) if payload_path.exists() else None,
        "static_report_path": None,
        "runs_dir": str(runs_dir) if runs_dir.exists() else None,
        "tables_dir": str(tables_dir) if tables_dir.exists() else None,
        "report_dir": str(report_dir) if report_dir.exists() else None,
        "figures_dir": str(report_dir / "figures") if (report_dir / "figures").exists() else None,
        "roi_csv": str(roi_csv_path) if roi_csv_path.exists() else None,
    }
    return artifacts


def _load_payload_from_path(payload_path: Path, output_tag: str) -> dict[str, Any]:
    with payload_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    tables_dir = payload_path.parent
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


def load_payload_for_run(run_id: str, output_tag: str | None = None) -> dict[str, Any]:
    if not output_tag:
        raise FileNotFoundError(f"No output tag is recorded for run {run_id}.")
    payload = locate_result_artifacts(output_tag).get("dashboard_payload")
    if not payload:
        raise FileNotFoundError(
            f"Results are not available for run {run_id}. Expected dashboard artifact "
            f"data/output/03_reports/report/{output_tag}/tables/dashboard_payload.json was not found."
        )
    return _load_payload_from_path(Path(str(payload)), output_tag)


def _relative_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _history_id_for_payload(path: Path) -> str:
    raw = _relative_path(path).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _payload_path_for_history_id(history_id: str) -> Path:
    try:
        padded = history_id + ("=" * (-len(history_id) % 4))
        rel = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except Exception as exc:
        raise FileNotFoundError("Saved result id is not valid.") from exc

    path = (PROJECT_ROOT / rel).resolve()
    reports_root = REPORTS_ROOT.resolve()
    try:
        path.relative_to(reports_root)
    except ValueError as exc:
        raise FileNotFoundError("Saved result id does not point to a report payload.") from exc
    if not path.is_file():
        raise FileNotFoundError("Saved result payload was not found.")
    if path.name != "dashboard_payload.json":
        raise FileNotFoundError("Saved result id does not point to a dashboard payload.")
    return path


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed


def _channels_from_payload(data: dict[str, Any]) -> list[str]:
    options = data.get("target_channel_detail", {}).get("options", [])
    channels: list[str] = []
    if isinstance(options, list):
        for option in options:
            if isinstance(option, dict):
                value = _string_or_none(option.get("label") or option.get("value"))
            else:
                value = _string_or_none(option)
            if value and value not in channels:
                channels.append(value)
    if not channels:
        workbench_channels = data.get("workbench", {}).get("available_channels", [])
        if isinstance(workbench_channels, list):
            channels = [channel for channel in (_string_or_none(item) for item in workbench_channels) if channel]
    return channels


def _history_item_from_payload_path(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    report_dir = path.parent.parent
    output_tag = report_dir.name
    identity_record: dict[str, Any] = {}
    try:
        from backend.app.services.saved_result_identity import list_index_records

        path_text = str(path)
        identity_record = next(
            (
                record for record in list_index_records()
                if record.get("output_tag") == output_tag
                or record.get("dashboard_path") == path_text
                or record.get("payload_path") == path_text
            ),
            {},
        )
    except Exception:
        identity_record = {}
    payload_rel = _relative_path(path)
    history_id = _history_id_for_payload(path)
    diagnostics = data.get("diagnostics_overview") or data.get("diagnostics", {}).get("overview") or {}
    overview = data.get("overview") or {}
    outcome = data.get("outcome_context") or {}
    meta = data.get("meta") or {}
    channels = _channels_from_payload(data)
    generated_at = _string_or_none(meta.get("generated_at"))
    if not generated_at:
        generated_at = _string_or_none(data.get("generated_at"))
    if not generated_at:
        generated_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()

    qc_pass = _int_or_none(diagnostics.get("pass_runs"))
    qc_review = _int_or_none(diagnostics.get("review_runs"))
    qc_fail = _int_or_none(diagnostics.get("fail_runs"))
    qc_mix = identity_record.get("qc_mix") if isinstance(identity_record.get("qc_mix"), dict) else {}
    return {
        "history_id": history_id,
        "run_id": output_tag,
        "output_tag": output_tag,
        "display_result_id": identity_record.get("display_result_id") or output_tag,
        "config_fingerprint": identity_record.get("config_fingerprint"),
        "original_csv_filename": identity_record.get("original_csv_filename"),
        "csv_name_prefix": identity_record.get("csv_name_prefix"),
        "dataset_hash": identity_record.get("dataset_hash"),
        "generated_at": generated_at,
        "completed_at": identity_record.get("completed_at"),
        "kpi": _string_or_none(outcome.get("metric_label") or outcome.get("kpi_type") or data.get("kpi")),
        "kpi_path": identity_record.get("kpi_path") or _string_or_none(outcome.get("metric_label") or outcome.get("kpi_type") or data.get("kpi")),
        "revenue_handling": identity_record.get("revenue_handling"),
        "channels": channels,
        "channel_count": len(channels) or (_int_or_none(overview.get("n_channels")) or 0),
        "completed_runs": _int_or_none(diagnostics.get("n_runs") or overview.get("n_rows")),
        "qc_pass_runs": _int_or_none(qc_mix.get("pass")) or qc_pass,
        "qc_review_runs": _int_or_none(qc_mix.get("review")) or qc_review,
        "qc_fail_runs": _int_or_none(qc_mix.get("fail")) or qc_fail,
        "qc_mix": {
            "pass": _int_or_none(qc_mix.get("pass")) or qc_pass or 0,
            "review": _int_or_none(qc_mix.get("review")) or qc_review or 0,
            "fail": _int_or_none(qc_mix.get("fail")) or qc_fail or 0,
        },
        "report_path": None,
        "static_report_path": None,
        "dashboard_path": identity_record.get("dashboard_path") or payload_rel,
        "payload_path": payload_rel,
        "react_result_url": f"/results/overview?history_id={history_id}",
    }


def list_saved_result_history() -> list[dict[str, Any]]:
    if not REPORTS_ROOT.exists():
        return []
    items = []
    for payload_path in REPORTS_ROOT.glob("**/dashboard_payload.json"):
        item = _history_item_from_payload_path(payload_path)
        if item:
            items.append(item)
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        key = str(item.get("display_result_id") or item.get("output_tag") or item.get("history_id"))
        existing = deduped.get(key)
        if not existing or str(item.get("generated_at") or "") > str(existing.get("generated_at") or ""):
            deduped[key] = item
    return sorted(deduped.values(), key=lambda item: str(item.get("generated_at") or ""), reverse=True)


def load_saved_history_payload(history_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    payload_path = _payload_path_for_history_id(history_id)
    item = _history_item_from_payload_path(payload_path)
    if not item:
        raise FileNotFoundError("Saved result payload is missing or malformed.")
    data = _load_payload_from_path(payload_path, item["output_tag"])
    return item, data
