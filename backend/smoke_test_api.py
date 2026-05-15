from __future__ import annotations

import argparse
from pathlib import Path
import sys

import httpx
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.main import app
from backend.app.services.paths import RUNS_DIR, UPLOADS_DIR, WORKFLOWS_DIR


def _cleanup(upload_id: str | None, workflow_id: str | None, run_id: str | None) -> None:
    if upload_id:
        for path in UPLOADS_DIR.glob(f"{upload_id}_*"):
            path.unlink(missing_ok=True)
    if workflow_id:
        (WORKFLOWS_DIR / f"{workflow_id}.json").unlink(missing_ok=True)
    if run_id:
        (RUNS_DIR / f"{run_id}.json").unlink(missing_ok=True)


def _client(base_url: str | None):
    if base_url:
        return httpx.Client(base_url=base_url, timeout=10.0)
    return TestClient(app)


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the BlueAlpha FastAPI boundary.")
    parser.add_argument("--base-url", help="Optional running API base URL, for example http://127.0.0.1:8000")
    parser.add_argument("--keep-artifacts", action="store_true", help="Keep the temporary upload/workflow/run records and print their ids.")
    args = parser.parse_args()

    client = _client(args.base_url)
    upload_id: str | None = None
    workflow_id: str | None = None
    run_id: str | None = None

    try:
        health = client.get("/api/health")
        assert health.status_code == 200, health.text
        assert health.json()["status"] == "ok"

        csv_bytes = (
            "date,subscriptions,meta_spend,google_spend,revenue\n"
            "2024-01-01,120,1000,900,4800\n"
            "2024-02-01,135,1100,950,5400\n"
        ).encode("utf-8")
        upload = client.post(
            "/api/uploads",
            files={"file": ("phase45_smoke.csv", csv_bytes, "text/csv")},
        )
        assert upload.status_code == 200, upload.text
        upload_id = upload.json()["upload_id"]

        profile = client.get(f"/api/uploads/{upload_id}/profile")
        assert profile.status_code == 200, profile.text
        profile_json = profile.json()
        assert profile_json["detected"]["time_candidates"]
        assert profile_json["detected"]["spend_channel_candidates"]

        workflow = client.post(
            "/api/workflows",
            json={
                "upload_id": upload_id,
                "name": "Phase 4.5 smoke workflow",
                "dataset": {"path": "backend/storage/uploads/phase45_smoke.csv"},
                "column_mapping": {
                    "time_col": "date",
                    "kpi_col": "subscriptions",
                    "channels": ["meta", "google"],
                },
                "outcome": {
                    "kpi_col": "subscriptions",
                    "kpi_type": "non_revenue",
                    "revenue_per_kpi": 40.0,
                },
                "prior_grid": {
                    "roi_mu_values": [0.5, 1.0],
                    "roi_sigma_values": [0.5],
                    "roi_dist_values": ["LogNormal"],
                },
            },
        )
        assert workflow.status_code == 200, workflow.text
        workflow_id = workflow.json()["workflow_id"]

        preview = client.post(f"/api/workflows/{workflow_id}/config/preview")
        assert preview.status_code == 200, preview.text
        preview_json = preview.json()
        assert preview_json["estimated_run_count"] == 4
        assert "run_mode: roi_full" in preview_json["yaml"]

        run = client.post(
            "/api/runs",
            json={
                "workflow_id": workflow_id,
                "approved_config_preview": preview_json,
            },
        )
        assert run.status_code == 200, run.text
        run_json = run.json()
        run_id = run_json["run_id"]
        assert run_json["status"] == "queued"
        assert run_json["progress"]["total_runs"] == 4

        status = client.get(f"/api/runs/{run_id}")
        assert status.status_code == 200, status.text
        assert status.json()["run_id"] == run_id

        logs = client.get(f"/api/runs/{run_id}/logs")
        assert logs.status_code == 200, logs.text
        assert logs.json()["run_id"] == run_id
        assert logs.json()["lines"]

        advanced = client.post(f"/api/runs/{run_id}/mock/advance")
        assert advanced.status_code == 200, advanced.text
        assert advanced.json()["status"] in {"running", "completed"}
        assert advanced.json()["progress"]["completed_runs"] > 0

        payload = client.get("/api/runs/demo_32run/results/payload")
        assert payload.status_code == 200, payload.text
        assert payload.json()["run_id"] == "demo_32run"
        assert isinstance(payload.json()["payload"], dict)

        target = args.base_url or "in-process TestClient"
        print(f"FastAPI smoke test passed against {target}.")
        if args.keep_artifacts:
            print(f"SMOKE_UPLOAD_ID={upload_id}")
            print(f"SMOKE_WORKFLOW_ID={workflow_id}")
            print(f"SMOKE_RUN_ID={run_id}")
    finally:
        client.close()
        if not args.keep_artifacts:
            _cleanup(upload_id, workflow_id, run_id)


if __name__ == "__main__":
    main()
