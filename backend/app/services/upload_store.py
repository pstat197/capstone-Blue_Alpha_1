from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.app.services.paths import STORAGE_ROOT, UPLOADS_DIR, ensure_storage_dirs

UPLOAD_MANIFEST_PATH = STORAGE_ROOT / "upload_manifest.json"
MANIFEST_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_upload_filename(filename: str | None) -> str:
    return (filename or "uploaded.csv").replace("/", "_").replace("\\", "_")


def upload_path(upload_id: str, filename: str | None) -> Path:
    return UPLOADS_DIR / f"{upload_id}_{safe_upload_filename(filename)}"


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _empty_manifest() -> dict[str, Any]:
    return {"version": MANIFEST_VERSION, "files": {}, "uploads": {}}


def read_manifest() -> dict[str, Any]:
    ensure_storage_dirs()
    if not UPLOAD_MANIFEST_PATH.exists():
        return _empty_manifest()
    try:
        raw = json.loads(UPLOAD_MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _empty_manifest()
    if not isinstance(raw, dict):
        return _empty_manifest()
    raw.setdefault("version", MANIFEST_VERSION)
    raw.setdefault("files", {})
    raw.setdefault("uploads", {})
    if not isinstance(raw["files"], dict):
        raw["files"] = {}
    if not isinstance(raw["uploads"], dict):
        raw["uploads"] = {}
    return raw


def write_manifest(manifest: dict[str, Any]) -> None:
    ensure_storage_dirs()
    UPLOAD_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def register_upload_bytes(data: bytes, original_filename: str | None) -> dict[str, Any]:
    ensure_storage_dirs()
    upload_id = f"upload_{uuid4().hex[:12]}"
    filename = original_filename or "uploaded.csv"
    digest = content_hash(data)
    manifest = read_manifest()
    files = manifest["files"]
    uploads = manifest["uploads"]

    existing = files.get(digest) if isinstance(files.get(digest), dict) else None
    canonical_path = Path(str(existing.get("canonical_path"))) if existing else None
    reused_existing = bool(canonical_path and canonical_path.exists())
    if not reused_existing:
        canonical_path = upload_path(upload_id, filename)
        canonical_path.write_bytes(data)
        files[digest] = {
            "content_hash": digest,
            "canonical_upload_id": upload_id,
            "canonical_path": str(canonical_path),
            "first_original_filename": filename,
            "first_uploaded_at": _now_iso(),
            "size_bytes": len(data),
        }

    upload_record = {
        "upload_id": upload_id,
        "content_hash": digest,
        "original_filename": filename,
        "stored_path": str(canonical_path),
        "uploaded_at": _now_iso(),
        "reused_existing": reused_existing,
        "size_bytes": len(data),
    }
    uploads[upload_id] = upload_record
    write_manifest(manifest)
    return upload_record


def resolve_upload(upload_id: str) -> tuple[Path, str]:
    manifest = read_manifest()
    record = manifest.get("uploads", {}).get(upload_id)
    if isinstance(record, dict):
        path = Path(str(record.get("stored_path") or ""))
        if path.exists():
            return path, str(record.get("original_filename") or path.name)

    matches = list(UPLOADS_DIR.glob(f"{upload_id}_*"))
    if not matches:
        raise FileNotFoundError(f"Upload not found: {upload_id}")
    path = matches[0]
    filename = path.name.removeprefix(f"{upload_id}_")
    return path, filename

