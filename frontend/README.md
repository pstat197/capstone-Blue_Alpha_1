# Frontend

React + TypeScript app for configuring, launching, monitoring, and reading BlueAlpha prior-sensitivity analyses.

The app is built with Vite and talks to the FastAPI backend when available. It also includes demo fallbacks so the UI remains usable during local development.

## Run Locally

Start the backend from the repository root:

```bash
uv venv .venv
uv pip install -r backend/requirements.txt
.venv/bin/uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend from `frontend/`:

```bash
npm install
npm run dev
```

Vite defaults to `http://127.0.0.1:5173`. If that port is occupied, Vite may choose another `517x` port; the backend allows local Vite ports `5170` through `5179`.

Build for production:

```bash
npm run build
npm run preview
```

The API base URL defaults to `http://127.0.0.1:8000`. Override it with:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

## App Structure

```text
src/
  api/               typed API clients
  app/               router, navigation, and app shell
  features/
    workflow/        pre-run setup pages
    run-monitor/     run status and logs
    results/         read-only result pages
  shared/            shared pages and contextual help
  styles.css         global styling
```

## User Flow

The main workflow is:

```text
upload/select data
  -> configure KPI and model assumptions
  -> preview generated config
  -> start mock or tiny real run
  -> monitor run status
  -> inspect completed results
```

Pre-run pages are configuration surfaces. Result pages are read-only views over generated `dashboard_payload.json` data.

## API Clients

Frontend API clients live under `src/api/`:

- `health.ts`: `GET /api/health`
- `uploads.ts`: CSV upload, example datasets, profile, and preview
- `workflows.ts`: draft workflow create/read/update and config preview
- `runs.ts`: create run, read run status, read logs, advance mock progress
- `results.ts`: result history and run payload lookup
- `types.ts`: shared TypeScript contracts for API responses

Pages should prefer these clients over direct `fetch` calls.

## Data Sources

The app deliberately distinguishes three data sources:

- API data: live responses from FastAPI
- bundled demo payload: generated report data bundled into the app for fallback result pages
- frontend mock data: local wizard defaults in `features/workflow/data/mockWorkflow.ts`

Result pages try `GET /api/runs/{run_id}/results/payload` first. When no run payload is available, demo routes can fall back to:

```text
data/output/03_reports/report/demo_32run/tables/dashboard_payload.json
```

Important result data files:

- `features/results/data/resultLoader.ts`: API-first payload loader and fallback behavior
- `features/results/data/resultTypes.ts`: payload shape used by the UI
- `features/results/data/resultSelectors.ts`: adapters from payload data to page-friendly values

## Page Groups

Workflow pages:

- welcome and rules
- new analysis upload
- KPI and revenue setup
- prior grid setup
- structural settings
- review and start run

Execution page:

- run monitor with status, progress, logs, and mock advance control

Result pages:

- overview
- prior sensitivity
- prior vs posterior
- scenario explorer
- model structure
- run audit and diagnostics
- history

## Run Modes In The UI

The review page exposes separate run actions:

- `Start Analysis (Mock)`: creates local mock state for UI testing and never runs Meridian.
- `Start Tiny Real Run`: calls the backend `real_tiny` launcher, which narrows the reviewed config to a very small pipeline run.

Full production-scale advisor-grid execution is intentionally not exposed as a normal frontend action in this branch.

## Development Notes

- Keep pre-run workflow pages focused on editable assumptions.
- Keep result pages read-only and payload-backed.
- Surface the current data source to avoid confusing demo fallbacks with completed run data.
- Use `src/api/` clients for backend communication.
- Keep generated pipeline artifacts out of the frontend source tree unless they are intentional demo fixtures.
