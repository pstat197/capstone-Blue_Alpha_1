from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from backend.app.services.paths import PROJECT_ROOT, RUNS_DIR, STORAGE_ROOT, UPLOADS_DIR, WORKFLOWS_DIR, ensure_storage_dirs
from backend.app.services.result_locator import locate_result_artifacts
from backend.app.services.upload_store import file_content_hash, read_manifest, write_manifest


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _age_days(path: Path, timestamp: Any = None) -> float:
    parsed = _parse_dt(timestamp)
    if parsed is None:
        parsed = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    return round(max(0.0, (_now() - parsed).total_seconds() / 86400.0), 3)


def _resolve_project_path(raw: Any) -> str | None:
    if raw in (None, "", "null", "none"):
        return None
    path = Path(str(raw))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _read_yaml(path: Path) -> dict[str, Any] | None:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return raw if isinstance(raw, dict) else None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _write_audit_log(report: dict[str, Any]) -> str:
    audit_dir = STORAGE_ROOT / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = audit_dir / f"storage_hygiene_upload_dedupe_{timestamp}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return str(path)


def _upload_id_from_path(path: Path) -> str | None:
    parts = path.name.split("_", 2)
    if len(parts) >= 2 and parts[0] == "upload":
        return "_".join(parts[:2])
    return None


def _filename_from_upload_path(path: Path) -> str:
    upload_id = _upload_id_from_path(path)
    if upload_id:
        return path.name.removeprefix(f"{upload_id}_")
    return path.name


def _storage_metadata_files() -> list[Path]:
    files: list[Path] = []
    for pattern in ("**/*.json", "**/*.yaml", "**/*.yml"):
        files.extend(path for path in STORAGE_ROOT.glob(pattern) if path.is_file())
    return sorted(path for path in files if not path.is_relative_to(UPLOADS_DIR) and path.name != "upload_manifest.json")


def _replace_path_strings(value: Any, replacements: dict[str, str]) -> tuple[Any, int]:
    if isinstance(value, dict):
        changed = 0
        out: dict[Any, Any] = {}
        for key, item in value.items():
            new_item, item_changed = _replace_path_strings(item, replacements)
            out[key] = new_item
            changed += item_changed
        return out, changed
    if isinstance(value, list):
        changed = 0
        out_list = []
        for item in value:
            new_item, item_changed = _replace_path_strings(item, replacements)
            out_list.append(new_item)
            changed += item_changed
        return out_list, changed
    if isinstance(value, str):
        resolved = _resolve_project_path(value)
        replacement = replacements.get(str(resolved))
        if replacement and value != replacement:
            return replacement, 1
    return value, 0


def _find_path_string_refs(value: Any, targets: set[str], refs: list[str], prefix: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _find_path_string_refs(item, targets, refs, f"{prefix}.{key}")
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            _find_path_string_refs(item, targets, refs, f"{prefix}[{idx}]")
    elif isinstance(value, str) and _resolve_project_path(value) in targets:
        refs.append(prefix)


def _metadata_references_to(paths: list[Path]) -> dict[str, list[dict[str, str]]]:
    targets = {str(path.resolve()) for path in paths if path.exists()}
    refs: dict[str, list[dict[str, str]]] = {target: [] for target in targets}
    if not targets:
        return refs

    for metadata_path in _storage_metadata_files():
        data = _read_json(metadata_path) if metadata_path.suffix == ".json" else _read_yaml(metadata_path)
        if data is None:
            continue
        pointers: list[str] = []
        _find_path_string_refs(data, targets, pointers)
        for pointer in pointers:
            # Re-resolve by walking again is overkill for tiny metadata; keep all pointers on each matching target.
            for target in targets:
                target_refs: list[str] = []
                _find_path_string_refs(data, {target}, target_refs)
                if pointer in target_refs:
                    refs[target].append({"metadata_path": str(metadata_path), "pointer": pointer})
    return refs


def _collect_references() -> dict[str, Any]:
    workflow_refs: dict[str, list[str]] = {}
    run_refs: dict[str, list[str]] = {}
    workflow_ids_referenced_by_runs: set[str] = set()

    for path in WORKFLOWS_DIR.glob("wf_*.json"):
        data = _read_json(path)
        if not data:
            continue
        workflow_id = str(data.get("workflow_id") or path.stem)
        upload_id = data.get("upload_id")
        if upload_id:
            workflow_refs.setdefault(str(upload_id), []).append(workflow_id)
        data_csv = _resolve_project_path((data.get("dataset") or {}).get("data_csv"))
        if data_csv:
            workflow_refs.setdefault(data_csv, []).append(workflow_id)

    for path in RUNS_DIR.glob("run_*.json"):
        data = _read_json(path)
        if not data:
            continue
        run_id = str(data.get("run_id") or path.stem)
        workflow_id = data.get("workflow_id")
        if workflow_id:
            workflow_ids_referenced_by_runs.add(str(workflow_id))
        config_path = data.get("config_path")
        config = _read_yaml(Path(str(config_path))) if config_path else None
        if not config:
            config = _read_yaml(RUNS_DIR / run_id / "config.yaml")
        data_csv = _resolve_project_path(((config or {}).get("model") or {}).get("data_csv"))
        if data_csv:
            run_refs.setdefault(data_csv, []).append(run_id)

    return {
        "workflow_refs": workflow_refs,
        "run_refs": run_refs,
        "workflow_ids_referenced_by_runs": workflow_ids_referenced_by_runs,
    }


def _duplicate_uploads(upload_files: list[Path]) -> list[dict[str, Any]]:
    by_hash: dict[str, list[Path]] = {}
    for path in upload_files:
        try:
            digest = file_content_hash(path)
        except OSError:
            continue
        by_hash.setdefault(digest, []).append(path)
    return [
        {
            "content_hash": digest,
            "count": len(paths),
            "files": [str(path) for path in sorted(paths)],
        }
        for digest, paths in sorted(by_hash.items(), key=lambda item: (-len(item[1]), item[0]))
        if len(paths) > 1
    ]


def _upload_groups(upload_files: list[Path]) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    for path in upload_files:
        try:
            digest = file_content_hash(path)
        except OSError:
            continue
        groups.setdefault(digest, []).append(path)
    return {digest: sorted(paths) for digest, paths in sorted(groups.items())}


def _iso_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")


def _choose_canonical_path(digest: str, paths: list[Path], manifest: dict[str, Any], refs: dict[str, list[dict[str, str]]]) -> Path:
    file_record = manifest.get("files", {}).get(digest)
    if isinstance(file_record, dict):
        manifest_path = Path(str(file_record.get("canonical_path") or ""))
        for path in paths:
            if path.resolve() == manifest_path.resolve() and path.exists():
                return path

    def score(path: Path) -> tuple[int, float, str]:
        ref_count = len(refs.get(str(path.resolve()), []))
        return (-ref_count, path.stat().st_mtime, path.name)

    return sorted(paths, key=score)[0]


def _build_legacy_upload_manifest(groups: dict[str, list[Path]], canonical_by_hash: dict[str, Path]) -> dict[str, Any]:
    manifest = read_manifest()
    files = manifest.setdefault("files", {})
    uploads = manifest.setdefault("uploads", {})
    manifest.setdefault("version", 1)

    for digest, paths in groups.items():
        canonical = canonical_by_hash[digest]
        canonical_upload_id = _upload_id_from_path(canonical)
        files[digest] = {
            "content_hash": digest,
            "canonical_upload_id": canonical_upload_id,
            "canonical_path": str(canonical),
            "first_original_filename": _filename_from_upload_path(canonical),
            "first_uploaded_at": _iso_from_mtime(canonical),
            "size_bytes": canonical.stat().st_size,
        }
        for path in paths:
            upload_id = _upload_id_from_path(path)
            if not upload_id:
                continue
            existing = uploads.get(upload_id) if isinstance(uploads.get(upload_id), dict) else {}
            uploads[upload_id] = {
                "upload_id": upload_id,
                "content_hash": digest,
                "original_filename": existing.get("original_filename") or _filename_from_upload_path(path),
                "stored_path": str(canonical),
                "uploaded_at": existing.get("uploaded_at") or _iso_from_mtime(path),
                "reused_existing": path.resolve() != canonical.resolve(),
                "size_bytes": path.stat().st_size,
                "legacy_physical_path": str(path) if path.resolve() != canonical.resolve() else None,
            }
    return manifest


def _rewrite_storage_metadata_paths(replacements: dict[str, str], *, apply: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not replacements:
        return rows
    for metadata_path in _storage_metadata_files():
        is_json = metadata_path.suffix == ".json"
        data = _read_json(metadata_path) if is_json else _read_yaml(metadata_path)
        if data is None:
            continue
        updated, change_count = _replace_path_strings(data, replacements)
        if not change_count:
            continue
        rows.append({"metadata_path": str(metadata_path), "path_references_updated": change_count})
        if apply:
            if is_json:
                _write_json(metadata_path, updated)
            else:
                _write_yaml(metadata_path, updated)
    return rows


def migrate_duplicate_uploads(*, apply: bool = False) -> dict[str, Any]:
    ensure_storage_dirs()
    upload_files = sorted(path for path in UPLOADS_DIR.glob("upload_*") if path.is_file())
    groups = _upload_groups(upload_files)
    manifest = read_manifest()
    refs_before = _metadata_references_to(upload_files)
    canonical_by_hash = {
        digest: _choose_canonical_path(digest, paths, manifest, refs_before)
        for digest, paths in groups.items()
    }
    duplicate_groups = {
        digest: paths
        for digest, paths in groups.items()
        if len(paths) > 1
    }
    duplicate_paths = [
        path
        for digest, paths in duplicate_groups.items()
        for path in paths
        if path.resolve() != canonical_by_hash[digest].resolve()
    ]
    replacements = {
        str(path.resolve()): str(canonical_by_hash[digest])
        for digest, paths in duplicate_groups.items()
        for path in paths
        if path.resolve() != canonical_by_hash[digest].resolve()
    }

    metadata_updates = _rewrite_storage_metadata_paths(replacements, apply=apply)
    planned_manifest = _build_legacy_upload_manifest(groups, canonical_by_hash)
    deleted: list[dict[str, Any]] = []
    unsafe: list[dict[str, Any]] = []

    if apply:
        write_manifest(planned_manifest)

    refs_after = (
        _metadata_references_to(duplicate_paths)
        if apply
        else {str(path.resolve()): [] for path in duplicate_paths}
    )
    for path in duplicate_paths:
        remaining_refs = refs_after.get(str(path.resolve()), [])
        row = {
            "path": str(path),
            "upload_id": _upload_id_from_path(path),
            "remaining_references": remaining_refs,
        }
        if remaining_refs:
            row["reason"] = "metadata still references this duplicate path"
            unsafe.append(row)
            continue
        if apply:
            try:
                path.unlink()
                deleted.append({**row, "deleted": True})
            except OSError as exc:
                unsafe.append({**row, "reason": f"delete failed: {exc}"})
        else:
            deleted.append({**row, "would_delete": True})

    group_reports = []
    for digest, paths in duplicate_groups.items():
        canonical = canonical_by_hash[digest]
        group_reports.append(
            {
                "content_hash": digest,
                "canonical_path": str(canonical),
                "canonical_upload_id": _upload_id_from_path(canonical),
                "duplicate_paths": [str(path) for path in paths if path.resolve() != canonical.resolve()],
                "all_upload_ids": [_upload_id_from_path(path) for path in paths],
            }
        )

    report = {
        "mode": "apply" if apply else "dry_run",
        "generated_at": _now().isoformat().replace("+00:00", "Z"),
        "summary": {
            "upload_file_count": len(upload_files),
            "unique_content_hash_count": len(groups),
            "duplicate_content_hash_count": len(duplicate_groups),
            "duplicate_physical_files": len(duplicate_paths),
            "metadata_files_to_update": len(metadata_updates),
            "physical_files_deleted" if apply else "physical_files_that_would_be_deleted": len(deleted),
            "unsafe_duplicate_files_kept": len(unsafe),
            "manifest_upload_count_after": len(planned_manifest.get("uploads", {})),
            "manifest_content_hash_count_after": len(planned_manifest.get("files", {})),
        },
        "duplicate_groups": group_reports,
        "metadata_updates": metadata_updates,
        "deleted" if apply else "would_delete": deleted,
        "unsafe_kept": unsafe,
    }
    if apply:
        report["audit_log_path"] = _write_audit_log(report)
    return report


def _unreferenced_uploads(upload_files: list[Path], refs: dict[str, Any]) -> list[dict[str, Any]]:
    workflow_refs = refs["workflow_refs"]
    run_refs = refs["run_refs"]
    manifest = read_manifest()
    upload_records = manifest.get("uploads", {}) if isinstance(manifest.get("uploads"), dict) else {}
    rows: list[dict[str, Any]] = []
    for path in sorted(upload_files):
        resolved = _resolve_project_path(str(path))
        upload_id = _upload_id_from_path(path)
        workflow_ref_ids = list(workflow_refs.get(str(upload_id), [])) + list(workflow_refs.get(str(resolved), []))
        run_ref_ids = list(run_refs.get(str(resolved), []))
        manifest_upload_ids = [
            upload_id_key
            for upload_id_key, record in upload_records.items()
            if isinstance(record, dict) and _resolve_project_path(record.get("stored_path")) == resolved
        ]
        manifest_ref_ids = [
            uid
            for uid in manifest_upload_ids
            if workflow_refs.get(uid)
        ]
        if workflow_ref_ids or run_ref_ids or manifest_ref_ids:
            continue
        rows.append(
            {
                "path": str(path),
                "upload_id": upload_id,
                "size_bytes": path.stat().st_size,
                "age_days": _age_days(path),
            }
        )
    return rows


def _abandoned_workflows(refs: dict[str, Any], workflow_retention_days: int) -> list[dict[str, Any]]:
    referenced = refs["workflow_ids_referenced_by_runs"]
    rows = []
    for path in sorted(WORKFLOWS_DIR.glob("wf_*.json")):
        data = _read_json(path)
        if not data:
            continue
        workflow_id = str(data.get("workflow_id") or path.stem)
        age_days = _age_days(path)
        if workflow_id in referenced or age_days < workflow_retention_days:
            continue
        rows.append(
            {
                "workflow_id": workflow_id,
                "path": str(path),
                "status": data.get("status"),
                "upload_id": data.get("upload_id"),
                "data_csv": (data.get("dataset") or {}).get("data_csv"),
                "age_days": age_days,
            }
        )
    return rows


def _failed_runs(retention_days: int) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(RUNS_DIR.glob("run_*.json")):
        data = _read_json(path)
        if not data or data.get("status") != "failed":
            continue
        age_days = _age_days(path, data.get("completed_at") or data.get("started_at") or data.get("created_at"))
        if age_days < retention_days:
            continue
        run_id = str(data.get("run_id") or path.stem)
        rows.append(
            {
                "run_id": run_id,
                "status_path": str(path),
                "work_dir": str(RUNS_DIR / run_id) if (RUNS_DIR / run_id).is_dir() else None,
                "workflow_id": data.get("workflow_id"),
                "output_tag": data.get("output_tag"),
                "completed_at": data.get("completed_at"),
                "age_days": age_days,
            }
        )
    return rows


def _completed_run_folders() -> list[dict[str, Any]]:
    rows = []
    for folder in sorted(path for path in RUNS_DIR.glob("run_*") if path.is_dir()):
        status_path = RUNS_DIR / f"{folder.name}.json"
        data = _read_json(status_path)
        if not data or data.get("status") != "completed":
            continue
        output_tag = data.get("output_tag")
        artifacts = locate_result_artifacts(str(output_tag or ""))
        has_report_payload = bool(artifacts.get("dashboard_payload"))
        rows.append(
            {
                "run_id": folder.name,
                "work_dir": str(folder),
                "status_path": str(status_path),
                "output_tag": output_tag,
                "history_id": data.get("history_id"),
                "dashboard_payload": artifacts.get("dashboard_payload"),
                "safe_to_delete_work_dir": has_report_payload,
                "safety_note": (
                    "Report/history payload exists in data/output; deleting the work dir would still remove config/log audit files."
                    if has_report_payload
                    else "Unsafe: no dashboard payload was found for this run output tag."
                ),
            }
        )
    return rows


def inspect_storage(*, failed_run_retention_days: int = 7, workflow_retention_days: int = 7) -> dict[str, Any]:
    ensure_storage_dirs()
    upload_files = sorted(path for path in UPLOADS_DIR.glob("upload_*") if path.is_file())
    refs = _collect_references()
    manifest = read_manifest()
    return {
        "mode": "dry_run",
        "generated_at": _now().isoformat().replace("+00:00", "Z"),
        "retention": {
            "failed_run_retention_days": failed_run_retention_days,
            "workflow_retention_days": workflow_retention_days,
        },
        "summary": {
            "upload_file_count": len(upload_files),
            "workflow_file_count": len(list(WORKFLOWS_DIR.glob("wf_*.json"))),
            "run_status_file_count": len(list(RUNS_DIR.glob("run_*.json"))),
            "run_work_dir_count": len([path for path in RUNS_DIR.glob("run_*") if path.is_dir()]),
            "manifest_upload_count": len(manifest.get("uploads", {})),
            "manifest_content_hash_count": len(manifest.get("files", {})),
        },
        "duplicate_uploads_by_content_hash": _duplicate_uploads(upload_files),
        "unreferenced_uploads": _unreferenced_uploads(upload_files, refs),
        "abandoned_workflow_drafts": _abandoned_workflows(refs, workflow_retention_days),
        "failed_runs_past_retention": _failed_runs(failed_run_retention_days),
        "completed_run_folders": _completed_run_folders(),
    }
