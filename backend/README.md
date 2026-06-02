# Backend

FastAPI service for the BlueAlpha React workflow. It handles CSV uploads, draft workflow state, config previews, run records, result payload lookup, and the guarded local pipeline launcher.

The frontend expects the API at `http://127.0.0.1:8000` unless `VITE_API_BASE_URL` is set.

## Run Locally

From the repository root:

```bash
uv venv .venv
uv pip install -r backend/requirements.txt
.venv/bin/uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

To enable `real_tiny` runs, the pipeline environment must also have the root modeling dependencies:

```bash
uv pip install --python .venv/bin/python -r requirements.txt
```

If Meridian/TensorFlow are installed in a different environment, point the backend launcher at that interpreter:

```bash
export BLUEALPHA_PIPELINE_PYTHON=/absolute/path/to/python
```

Run the API smoke test:

```bash
.venv/bin/python backend/smoke_test_api.py
.venv/bin/python backend/smoke_test_api.py --base-url http://127.0.0.1:8000
```

## API Surface

Health:

- `GET /api/health`

Uploads and example datasets:

- `POST /api/uploads`
- `POST /api/uploads/examples/monthly-mocha`
- `POST /api/uploads/examples/runnable-demo`
- `GET /api/uploads/templates/blank`
- `GET /api/uploads/examples/schema-preview`
- `GET /api/uploads/examples/runnable-demo`
- `GET /api/uploads/{upload_id}/profile`
- `GET /api/uploads/{upload_id}/preview`

Workflow drafts:

- `POST /api/workflows`
- `GET /api/workflows/{workflow_id}`
- `PATCH /api/workflows/{workflow_id}`
- `POST /api/workflows/{workflow_id}/config/preview`

Runs:

- `POST /api/runs`
- `GET /api/runs/latest-completed`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/logs`
- `POST /api/runs/{run_id}/mock/advance`

Results:

- `GET /api/results/history`
- `GET /api/results/history/{history_id}`
- `DELETE /api/results/history/{history_id}`
- `GET /api/runs/{run_id}/results/payload`
- `GET /api/runs/{run_id}/results`

## Local Storage

Backend state is file-backed so the app can run locally without a database.

```text
backend/storage/
  uploads/       uploaded CSV files
  workflows/     workflow draft JSON files
  runs/          run status JSON, generated configs, and run logs
```

Upload deduplication is tracked in `backend/storage/upload_manifest.json` by SHA-256 content hash. Result history identities are tracked by `backend/app/services/saved_result_identity.py` and related storage helpers.

Inspect storage hygiene without changing files:

```bash
.venv/bin/python -m backend.storage_hygiene
.venv/bin/python -m backend.storage_hygiene --dedupe-uploads
```

Add `--apply` only when you intentionally want the hygiene task to rewrite metadata or remove duplicate upload files.

## Run Modes

`POST /api/runs` supports separate execution modes:

- `mock`: creates local run state and lets the frontend advance progress for UI testing. It never imports Meridian or starts the modeling pipeline.
- `real_tiny`: writes a run-specific config and launches `python -m src.pipeline` in a background process with strict limits.
- `real_full`: present in service code for future work, but not the normal UI path for this PR.

For `real_tiny`, the backend narrows the approved config to one target channel, one `roi_mu`, one `roi_sigma`, one prior distribution, and one worker. Output tags use `phase5a_tiny_{run_id}`.

The launcher writes:

```text
backend/storage/runs/{run_id}/config.yaml
backend/storage/runs/{run_id}/run.log
```

Expected pipeline artifacts:

```text
data/output/01_runs/{tag}/
data/output/02_tables/{tag}/
data/output/03_reports/report/{tag}/tables/dashboard_payload.json
```

## Frontend Behavior

The frontend is API-first but has fallbacks:

- health failures show fallback mode in the shell
- upload/profile failures use demo dataset assumptions
- config-preview failures use local mock workflow state
- result payload failures use the bundled demo payload where appropriate

Local Vite origins on `127.0.0.1` or `localhost` ports `5170` through `5179` are allowed by CORS.

## Key Files

- `app/main.py`: FastAPI app, CORS, router registration, health endpoint
- `app/api/`: route handlers grouped by uploads, workflows, runs, and results
- `app/schemas/`: Pydantic request/response contracts
- `app/services/config_builder.py`: workflow draft to pipeline config preview
- `app/services/pipeline_launcher.py`: guarded subprocess launcher and progress parsing
- `app/services/result_locator.py`: result payload and artifact lookup
- `app/services/*_store.py`: local file-backed state stores
- `smoke_test_api.py`: end-to-end API smoke test
