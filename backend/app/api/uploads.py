from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from backend.app.schemas.upload import CsvPreview, CsvProfile, UploadResponse
from backend.app.services.csv_profiler import profile_csv
from backend.app.services.paths import PROJECT_ROOT, ensure_storage_dirs
from backend.app.services.upload_store import register_upload_bytes, resolve_upload

router = APIRouter(tags=["uploads"])


def _find_uploaded_csv(upload_id: str):
    try:
        return resolve_upload(upload_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Upload not found: {upload_id}")


@router.post("/uploads", response_model=UploadResponse)
async def create_upload(file: UploadFile = File(...)) -> UploadResponse:
    ensure_storage_dirs()
    record = register_upload_bytes(await file.read(), file.filename or "uploaded.csv")
    upload_id = str(record["upload_id"])
    return UploadResponse(
        upload_id=upload_id,
        filename=str(record["original_filename"]),
        profile_url=f"/api/uploads/{upload_id}/profile",
        content_hash=str(record["content_hash"]),
        storage_path=str(record["stored_path"]),
        reused_existing=bool(record["reused_existing"]),
        uploaded_at=str(record["uploaded_at"]),
    )


@router.post("/uploads/examples/monthly-mocha", response_model=UploadResponse)
def load_monthly_mocha_example() -> UploadResponse:
    ensure_storage_dirs()
    source = PROJECT_ROOT / "data" / "raw" / "monthly_mocha.csv"
    if not source.exists():
        raise HTTPException(status_code=404, detail="Example dataset not found: monthly_mocha.csv")
    filename = "monthly_mocha.csv"
    record = register_upload_bytes(source.read_bytes(), filename)
    upload_id = str(record["upload_id"])
    return UploadResponse(
        upload_id=upload_id,
        filename=filename,
        profile_url=f"/api/uploads/{upload_id}/profile",
        content_hash=str(record["content_hash"]),
        storage_path=str(record["stored_path"]),
        reused_existing=bool(record["reused_existing"]),
        uploaded_at=str(record["uploaded_at"]),
    )


@router.get("/uploads/{upload_id}/profile", response_model=CsvProfile)
def get_upload_profile(upload_id: str) -> CsvProfile:
    ensure_storage_dirs()
    path, filename = _find_uploaded_csv(upload_id)
    try:
        return profile_csv(upload_id=upload_id, filename=filename, path=path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to profile CSV: {exc}") from exc


@router.get("/uploads/{upload_id}/preview", response_model=CsvPreview)
def get_upload_preview(upload_id: str, limit: int = Query(default=10, ge=1, le=100)) -> CsvPreview:
    ensure_storage_dirs()
    path, filename = _find_uploaded_csv(upload_id)
    try:
        df = pd.read_csv(path, nrows=limit).where(pd.notna, None)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to preview CSV: {exc}") from exc

    rows = df.to_dict(orient="records")
    return CsvPreview(upload_id=upload_id, filename=filename, columns=list(df.columns), rows=rows, limit=limit)
