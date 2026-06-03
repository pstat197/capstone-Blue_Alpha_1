from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import results, runs, uploads, workflows

SERVICE_NAME = "bluealpha-prior-sensitivity-api"

app = FastAPI(title="BlueAlpha Prior Sensitivity API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://127.0.0.1:5174", "http://localhost:5173", "http://localhost:5174", "https://bluealpha-dashboard-frontend.onrender.com"],
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost):517[0-9]",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


app.include_router(uploads.router, prefix="/api")
app.include_router(workflows.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(results.router, prefix="/api")
