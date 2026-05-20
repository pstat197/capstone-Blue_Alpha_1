from __future__ import annotations

import base64
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.services.paths import PROJECT_ROOT, STORAGE_ROOT, ensure_storage_dirs
from backend.app.services.result_locator import locate_result_artifacts

INDEX_PATH = STORAGE_ROOT / "saved_results_index.json"
PIPELINE_SCHEMA_VERSION = "saved-result-identity-v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_csv_prefix(filename: str | None) -> str:
    stem = Path(filename or "dataset").stem.lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", stem)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "dataset"


def _original_filename_from_path(path: str | None) -> str:
    if not path:
        return "dataset.csv"
    name = Path(path).name
    match = re.match(r"^upload_[0-9a-f]{12}_(.+)$", name)
    return match.group(1) if match else name


def _sha256_file(path: str | None) -> str:
    if not path:
        return ""
    file_path = Path(path)
    if not file_path.exists():
        return ""
    digest = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _semantic_config(config: dict[str, Any], dataset_hash: str, csv_name_prefix: str) -> dict[str, Any]:
    model = config.get("model") if isinstance(config.get("model"), dict) else {}
    run_mode = str(config.get("run_mode", "roi_full"))
    return {
        "pipeline_schema_version": PIPELINE_SCHEMA_VERSION,
        "dataset_hash": dataset_hash,
        "csv_name_prefix": csv_name_prefix,
        "run_mode": run_mode,
        "parallel_workers": config.get("parallel_workers"),
        "model": {
            "channels": model.get("channels"),
            "time_col": model.get("time_col"),
            "geo_col": model.get("geo_col"),
            "population_col": model.get("population_col"),
        },
        "outcome": config.get("outcome"),
        "prior_mode": config.get("prior_mode"),
        "run_modes": config.get("run_modes"),
        "defaults": config.get("defaults"),
        "structural": config.get("structural"),
        "sampler": config.get("sampler"),
        "sweep": config.get("sweep"),
    }


def compute_result_identity(config: dict[str, Any]) -> dict[str, Any]:
    model = config.get("model") if isinstance(config.get("model"), dict) else {}
    data_csv = str(model.get("data_csv") or "")
    original_csv_filename = _original_filename_from_path(data_csv)
    csv_name_prefix = normalize_csv_prefix(original_csv_filename)
    dataset_hash = _sha256_file(data_csv)
    semantic = _semantic_config(config, dataset_hash, csv_name_prefix)
    fingerprint = "cfg_" + hashlib.sha256(_canonical_json(semantic).encode("utf-8")).hexdigest()[:12]
    return {
        "display_result_id": None,
        "config_fingerprint": fingerprint,
        "original_csv_filename": original_csv_filename,
        "csv_name_prefix": csv_name_prefix,
        "dataset_hash": dataset_hash,
        "semantic_config": semantic,
    }


def _read_index() -> list[dict[str, Any]]:
    ensure_storage_dirs()
    if not INDEX_PATH.exists():
        return []
    try:
        raw = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return raw if isinstance(raw, list) else []


def _write_index(items: list[dict[str, Any]]) -> None:
    ensure_storage_dirs()
    INDEX_PATH.write_text(json.dumps(items, indent=2, sort_keys=True), encoding="utf-8")


def _history_id_for_payload_path(path: str | None) -> str | None:
    if not path:
        return None
    try:
        rel = Path(path).resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except Exception:
        return None
    return base64.urlsafe_b64encode(rel.encode("utf-8")).decode("ascii").rstrip("=")


def _record_is_completed(record: dict[str, Any]) -> bool:
    dashboard_path = record.get("dashboard_path") or record.get("payload_path")
    return record.get("status") == "completed" and bool(dashboard_path) and Path(str(dashboard_path)).exists()


def find_completed_by_fingerprint(config_fingerprint: str) -> dict[str, Any] | None:
    for record in _read_index():
        if record.get("config_fingerprint") == config_fingerprint and _record_is_completed(record):
            return record
    return None


def _next_display_result_id(csv_name_prefix: str, records: list[dict[str, Any]]) -> str:
    pattern = re.compile(rf"^{re.escape(csv_name_prefix)}_(\d+)$")
    used = []
    for record in records:
        display_id = str(record.get("display_result_id") or "")
        match = pattern.match(display_id)
        if match:
            used.append(int(match.group(1)))
    return f"{csv_name_prefix}_{(max(used) + 1) if used else 1:02d}"


def prepare_result_identity(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    identity = compute_result_identity(config)
    existing = find_completed_by_fingerprint(str(identity["config_fingerprint"]))
    if existing:
        identity["display_result_id"] = existing.get("display_result_id")
        return identity, existing

    records = _read_index()
    identity["display_result_id"] = _next_display_result_id(str(identity["csv_name_prefix"]), records)
    return identity, None


def _runs_csv_path(output_tag: str | None) -> Path | None:
    if not output_tag:
        return None
    runs_dir = PROJECT_ROOT / "data" / "output" / "01_runs" / output_tag
    matches = sorted(runs_dir.glob(f"prior_sensitivity_runs_*{output_tag}.csv")) if runs_dir.exists() else []
    return matches[0] if matches else None


def _qc_mix_from_payload(payload_path: str | None) -> dict[str, int]:
    if not payload_path:
        return {"pass": 0, "review": 0, "fail": 0}
    try:
        data = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    except Exception:
        return {"pass": 0, "review": 0, "fail": 0}
    overview = data.get("diagnostics_overview") or data.get("diagnostics", {}).get("overview") or {}
    return {
        "pass": int(overview.get("pass_runs") or 0),
        "review": int(overview.get("review_runs") or 0),
        "fail": int(overview.get("fail_runs") or 0),
    }


def _completed_runs_from_csv(output_tag: str | None) -> int | None:
    path = _runs_csv_path(output_tag)
    if not path:
        return None
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            return sum(1 for _ in csv.DictReader(f))
    except Exception:
        return None


def revenue_handling_from_config(config: dict[str, Any]) -> str | None:
    outcome = config.get("outcome") if isinstance(config.get("outcome"), dict) else {}
    revenue_col = outcome.get("revenue_col")
    revenue_per_kpi = outcome.get("revenue_per_kpi")
    if revenue_col:
        return "direct revenue column"
    if revenue_per_kpi is not None:
        return f"revenue_per_kpi = {revenue_per_kpi}"
    return None


def kpi_path_from_config(config: dict[str, Any]) -> str | None:
    outcome = config.get("outcome") if isinstance(config.get("outcome"), dict) else {}
    if outcome.get("kpi_type") == "non_revenue":
        return "Revenue-equivalent ROI"
    if outcome.get("revenue_col"):
        return "Direct revenue ROI"
    return str(outcome.get("roi_mode") or outcome.get("kpi_type") or "") or None


def register_completed_result(status: Any, config: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not getattr(status, "display_result_id", None) or not getattr(status, "config_fingerprint", None):
        return None
    config = config or {}
    artifacts = locate_result_artifacts(getattr(status, "output_tag", "") or "")
    dashboard_path = artifacts.get("dashboard_payload")
    if not dashboard_path:
        return None

    record = {
        "display_result_id": status.display_result_id,
        "config_fingerprint": status.config_fingerprint,
        "original_csv_filename": status.original_csv_filename,
        "csv_name_prefix": status.csv_name_prefix,
        "dataset_hash": status.dataset_hash,
        "status": "completed",
        "generated_at": status.completed_at or _now_iso(),
        "completed_at": status.completed_at or _now_iso(),
        "kpi": (config.get("outcome") or {}).get("kpi_col") if isinstance(config.get("outcome"), dict) else None,
        "kpi_path": kpi_path_from_config(config),
        "revenue_handling": revenue_handling_from_config(config),
        "channels": [channel.channel for channel in status.channel_progress],
        "completed_runs": status.progress.completed_runs or _completed_runs_from_csv(status.output_tag),
        "qc_mix": _qc_mix_from_payload(str(dashboard_path)),
        "report_path": None,
        "static_report_path": None,
        "dashboard_path": str(dashboard_path),
        "payload_path": str(dashboard_path),
        "history_id": _history_id_for_payload_path(str(dashboard_path)),
        "run_id": status.run_id,
        "output_tag": status.output_tag,
    }
    if record["history_id"]:
        record["react_result_url"] = f"/results/overview?history_id={record['history_id']}"

    records = [
        item for item in _read_index()
        if item.get("config_fingerprint") != record["config_fingerprint"]
        and item.get("display_result_id") != record["display_result_id"]
    ]
    records.append(record)
    _write_index(sorted(records, key=lambda item: str(item.get("generated_at") or ""), reverse=True))
    return record


def list_index_records() -> list[dict[str, Any]]:
    return _read_index()
