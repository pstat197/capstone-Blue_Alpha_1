from __future__ import annotations

from uuid import uuid4
from shutil import copyfile

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from backend.app.schemas.upload import CsvPreview, CsvProfile, UploadResponse
from backend.app.services.csv_profiler import profile_csv
from backend.app.services.paths import PROJECT_ROOT, UPLOADS_DIR, ensure_storage_dirs

router = APIRouter(tags=["uploads"])


def _upload_path(upload_id: str, filename: str):
    safe_filename = filename.replace("/", "_").replace("\\", "_")
    return UPLOADS_DIR / f"{upload_id}_{safe_filename}"


def _find_uploaded_csv(upload_id: str):
    matches = list(UPLOADS_DIR.glob(f"{upload_id}_*"))
    if not matches:
        raise HTTPException(status_code=404, detail=f"Upload not found: {upload_id}")
    path = matches[0]
    filename = path.name.removeprefix(f"{upload_id}_")
    return path, filename


@router.post("/uploads", response_model=UploadResponse)
async def create_upload(file: UploadFile = File(...)) -> UploadResponse:
    ensure_storage_dirs()
    upload_id = f"upload_{uuid4().hex[:12]}"
    path = _upload_path(upload_id, file.filename or "uploaded.csv")
    path.write_bytes(await file.read())
    return UploadResponse(upload_id=upload_id, filename=file.filename or "uploaded.csv", profile_url=f"/api/uploads/{upload_id}/profile")


@router.post("/uploads/examples/monthly-mocha", response_model=UploadResponse)
def load_monthly_mocha_example() -> UploadResponse:
    ensure_storage_dirs()
    source = PROJECT_ROOT / "data" / "raw" / "monthly_mocha.csv"
    if not source.exists():
        raise HTTPException(status_code=404, detail="Example dataset not found: monthly_mocha.csv")
    upload_id = f"upload_{uuid4().hex[:12]}"
    filename = "monthly_mocha.csv"
    destination = _upload_path(upload_id, filename)
    copyfile(source, destination)
    return UploadResponse(upload_id=upload_id, filename=filename, profile_url=f"/api/uploads/{upload_id}/profile")


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
