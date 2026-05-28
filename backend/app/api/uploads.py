from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile

from backend.app.schemas.upload import CsvPreview, CsvProfile, UploadResponse
from backend.app.services.csv_profiler import profile_csv
from backend.app.services.example_datasets import blank_template_csv, runnable_demo_csv, schema_preview_csv
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


@router.get("/uploads/templates/blank")
def download_blank_template() -> Response:
    return Response(
        content=blank_template_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="meridian_blank_template.csv"'},
    )


@router.get("/uploads/examples/schema-preview")
def download_schema_preview() -> Response:
    return Response(
        content=schema_preview_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="meridian_schema_preview.csv"'},
    )


@router.get("/uploads/examples/runnable-demo")
def download_runnable_demo() -> Response:
    return Response(
        content=runnable_demo_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="meridian_runnable_demo_156_weeks.csv"'},
    )


@router.post("/uploads/examples/runnable-demo", response_model=UploadResponse)
def load_runnable_demo_example() -> UploadResponse:
    ensure_storage_dirs()
    filename = "meridian_runnable_demo_156_weeks.csv"
    record = register_upload_bytes(runnable_demo_csv().encode("utf-8"), filename)
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
