# BlueAlpha FastAPI Boundary

FastAPI scaffold for the React product workflow.

This backend keeps mock mode intact and adds a guarded Phase 5A `real_tiny` launcher path. Full advisor-grid execution is still disabled.

The React frontend expects this API at `http://127.0.0.1:8000` by default. Override the frontend target with `VITE_API_BASE_URL` if needed.

## Current Endpoints

- `GET /api/health`
- `POST /api/uploads`
- `GET /api/uploads/{upload_id}/profile`
- `POST /api/workflows`
- `GET /api/workflows/{workflow_id}`
- `PATCH /api/workflows/{workflow_id}`
- `POST /api/workflows/{workflow_id}/config/preview`
- `POST /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/logs`
- `POST /api/runs/{run_id}/mock/advance`
- `GET /api/runs/{run_id}/results/payload`

## Local State

- Uploaded CSVs are stored under `backend/storage/uploads/`.
- Workflow drafts are stored under `backend/storage/workflows/`.
- Mock run records are stored under `backend/storage/runs/`.
- Tiny real run working directories are stored under `backend/storage/runs/{run_id}/`.
- Tiny real run configs and logs are stored at `backend/storage/runs/{run_id}/config.yaml` and `backend/storage/runs/{run_id}/run.log`.
- The demo result payload is read from the existing generated report artifact:
  `data/output/03_reports/report/demo_32run/tables/dashboard_payload.json`

## How To Run Locally

From the repository root, create the API-only backend environment:

```bash
uv venv .venv
uv pip install -r backend/requirements.txt
```

For Phase 5A.5 tiny real execution, the same `.venv` can also be the modeling runtime. Install the full repo requirements:

```bash
uv pip install --python .venv/bin/python -r requirements.txt
```

Equivalent `venv`/`pip` setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

For `venv`/`pip` modeling installs, use the root `requirements.txt` after the backend requirements.

Run the backend:

```bash
.venv/bin/uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Run the React app in a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Vite serves the app at `http://127.0.0.1:5173`.

The backend allows local Vite origins on `127.0.0.1` or `localhost` ports `5170` through `5179`, so API calls still work if Vite rolls to `5174` or `5175`.

Run the API smoke test:

```bash
.venv/bin/python backend/smoke_test_api.py
```

Against a running backend:

```bash
.venv/bin/python backend/smoke_test_api.py --base-url http://127.0.0.1:8000
```

## Mock Run Lifecycle

Phase 4 adds a run lifecycle without launching Meridian:

1. `POST /api/runs` accepts a `workflow_id` plus the approved config preview.
2. The backend validates that the workflow draft exists.
3. A local mock run record is written with `status: queued`.
4. `GET /api/runs/{run_id}` returns stored status/progress.
5. `POST /api/runs/{run_id}/mock/advance` updates local JSON state through `queued -> running -> completed`.

The mock progress endpoint is only for frontend testing. It does not import `src.main`, `src.pipeline`, call subprocesses, or run Meridian.

## Phase 5A Tiny Real Execution

`POST /api/runs` also accepts `mode: "real_tiny"`:

```json
{
  "workflow_id": "workflow_...",
  "mode": "real_tiny",
  "approved_config_preview": {
    "normalized_config": {}
  }
}
```

The intended local modeling interpreter is `.venv/bin/python` after installing root `requirements.txt`. If the working Meridian/TensorFlow stack lives somewhere else, point the launcher at it:

```bash
export BLUEALPHA_PIPELINE_PYTHON=/absolute/path/to/python
```

The launcher writes a run-specific config and starts this command:

```bash
.venv/bin/python -m src.pipeline --config backend/storage/runs/{run_id}/config.yaml --dollars-per-subscription 40
```

By default the launcher uses `BLUEALPHA_PIPELINE_PYTHON` when set, then `.venv/bin/python`, then the current backend interpreter. Use `BLUEALPHA_PIPELINE_PYTHON` if the modeling stack lives in a different environment from the backend API dependencies.

Manual one-run verification command from the repo root:

```bash
env \
  BLUEALPHA_CACHE_DIR="$PWD/.cache" \
  MPLCONFIGDIR="$PWD/.cache/matplotlib" \
  XDG_CACHE_HOME="$PWD/.cache" \
  ARVIZ_HOME="$PWD/.cache/arviz" \
  .venv/bin/python -m src.pipeline \
    --config /private/tmp/bluealpha_phase5a_manual_config.yaml \
    --dollars-per-subscription 40
```

Safety guardrails:

- The only enabled real mode is `real_tiny`.
- The generated config is forced to one target channel, one `roi_mu`, one `roi_sigma`, one distribution, and one worker.
- The output tag is always `phase5a_tiny_{run_id}`.
- The backend refuses Phase 5A configs estimated above 3 runs.
- Full 240-run advisor-grid execution is not enabled.

Inspect status with:

```bash
curl http://127.0.0.1:8000/api/runs/{run_id}
curl http://127.0.0.1:8000/api/runs/{run_id}/logs
```

After completion, the run status includes artifact paths when produced:

- `dashboard_payload`
- `report_html`
- `runs_dir`
- `tables_dir`
- `figures_dir`
- `tornado_outputs_dir`

If `dashboard_payload.json` exists, `result_url` points to `/results/overview?run_id={run_id}`. If the tiny pipeline fails, the monitor still shows `failed` plus the captured log output.

Common failure modes:

- Dependency/environment issue: missing imports such as `platformdirs`, `tensorflow`, `tensorflow_probability`, or `meridian`. Install root `requirements.txt` into `.venv` or set `BLUEALPHA_PIPELINE_PYTHON`.
- Config validation issue: invalid channel names, missing dataset columns, missing `revenue_per_kpi`, or invalid prior/structural config.
- Pipeline runtime issue: Meridian/model fitting raises after the subprocess starts. Inspect `backend/storage/runs/{run_id}/run.log`.
- Missing output artifact issue: the subprocess exits successfully, but `dashboard_payload.json` or report artifacts are absent. Check `data/output/03_reports/report/phase5a_tiny_{run_id}/`.

Run status schema:

- `run_id`, `workflow_id`, `status`
- `created_at`, `started_at`, `completed_at`
- `progress.total_runs`, `progress.completed_runs`, `progress.failed_runs`
- `progress.active_target_channel`, `progress.active_mu`, `progress.active_sigma`, `progress.active_dist`
- `channel_progress[]`: `channel`, `total_runs`, `completedRuns`, `failedRuns`, `status`
- `messages[]`, `monitor_url`, optional `result_url`, and `mode`

Deferred real-execution work:

- cancellation
- structured progress events beyond log polling
- full advisor-grid execution

## Frontend Fallback Behavior

The frontend is API-first for safe surfaces, but remains usable if FastAPI is down:

- App shell calls `GET /api/health` and labels the backend as reachable or fallback mode.
- Upload page uses `POST /api/uploads` and `GET /api/uploads/{upload_id}/profile` for uploaded CSVs; otherwise it keeps the Mocha demo profile.
- Review & Start Run creates a draft workflow and calls `POST /api/workflows/{workflow_id}/config/preview`; otherwise it shows the mock YAML preview.
- Review & Start Run can call `POST /api/runs` as either `Start Analysis (Mock)` or guarded `Start Tiny Real Run`.
- Run Monitor reads `GET /api/runs/{run_id}` and can manually advance mock progress for testing.
- Results pages call `GET /api/runs/{run_id}/results/payload`; otherwise they use the bundled demo `dashboard_payload.json`.

## Deferred Work

Full 240-run execution, cancellation, and production `sensitivity.yaml` writes remain deferred. The React controls are intentionally separate: `Start Analysis (Mock)` and `Start Tiny Real Run`.

## Current Execution Status

- Mock mode works and remains separate from real execution.
- `real_tiny` mode works through the API launcher and completed repeatability tests.
- Full 240-run advisor-grid execution is disabled. The public run schema accepts only `mock` or `real_tiny`; generated real-tiny configs are forced to one target/channel prior point and checked against `MAX_PHASE5A_REAL_RUNS = 3`.
- Verified successful runs include `run_812a6bbc9bd9`, `run_bfb9120d327a`, `run_31148e5f67db`, and `run_ccf8847b30bc`.
- Intentional failure check: `run_1419024aee3d` failed with a readable config-validation classification and no result URL.
- Known limitation: a one-point tiny run can produce limited sensitivity/tornado outputs because there are no non-baseline grid rows. Dashboard payload/report generation still completes.
- Known limitation: React result pages are payload-backed for real runs via `GET /api/runs/{run_id}/results/payload`; static figure asset loading is still demo/static until run-specific asset serving is added.
