from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "backend"
STORAGE_ROOT = BACKEND_ROOT / "storage"
UPLOADS_DIR = STORAGE_ROOT / "uploads"
WORKFLOWS_DIR = STORAGE_ROOT / "workflows"
RUNS_DIR = STORAGE_ROOT / "runs"
RUN_WORKDIRS_DIR = RUNS_DIR


def ensure_storage_dirs() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
