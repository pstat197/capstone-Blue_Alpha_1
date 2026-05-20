# BlueAlpha React Frontend

React + TypeScript product shell for the BlueAlpha prior-sensitivity workflow.

This app is connected to the FastAPI boundary where it is safe to do so. Mock execution remains available, and Phase 5A adds a guarded `Start Tiny Real Run` path. Full 240-run advisor-grid execution is still disabled. The generated HTML dashboard remains a compatibility artifact.

## Page Groups

- Pre-run workflow pages configure analysis inputs that will eventually map to `sensitivity.yaml`.
- Execution pages monitor submitted mock runs without changing assumptions or launching Meridian.
- Post-run result pages explore completed outputs such as `dashboard_payload.json` and output tables.

## How To Run Locally

Backend from the repository root:

```bash
uv venv .venv
uv pip install -r backend/requirements.txt
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

The root `requirements.txt` install is required for `Start Tiny Real Run` because it includes Meridian/TensorFlow/reporting dependencies. If those dependencies live in a different Python environment, start the backend with:

```bash
export BLUEALPHA_PIPELINE_PYTHON=/absolute/path/to/python
```

Frontend from `frontend/`:

```bash
npm install
npm run dev
npm run build
```

By default Vite runs at `http://127.0.0.1:5173`. If that port is occupied, Vite may roll to another `517x` port; the backend allows local Vite ports `5170` through `5179`.

The frontend expects FastAPI at:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

If `VITE_API_BASE_URL` is not set, `src/api/client.ts` uses `http://127.0.0.1:8000`.

Smoke-test the backend from the repository root:

```bash
.venv/bin/python backend/smoke_test_api.py
.venv/bin/python backend/smoke_test_api.py --base-url http://127.0.0.1:8000
```

## Current React Data Contract

There are three deliberately separate data layers:

- **API data:** health, upload profiling, workflow config preview, mock run lifecycle, and demo result payload are loaded from FastAPI when it is reachable.
- **Bundled demo payload:** post-run result pages fall back to the generated `dashboard_payload.json` bundled into the React app when FastAPI is unavailable.
- **Frontend mock data:** pre-run wizard defaults still come from `src/features/workflow/data/mockWorkflow.ts` when no upload/profile/config-preview API response is available.

Result pages try the API first:

- Endpoint: `GET /api/runs/{run_id}/results/payload`
- Fallback payload: `data/output/03_reports/report/demo_32run/tables/dashboard_payload.json`
- Loader/hook: `src/features/results/data/resultLoader.ts`

The fallback is intentional: the frontend remains usable without the backend while making the data source visible in each result page.

Types and selectors:

- Types: `src/features/results/data/resultTypes.ts`
- Selectors/adapters: `src/features/results/data/resultSelectors.ts`

Selector usage by page:

- Overview: `selectOverviewStats`, `selectLargestSelfResponse`, `selectSelfResponseTornadoRows`, `selectDiagnosticContext`
- Prior Sensitivity: `selectSelfResponseTornadoRows`, `selectDollarTornadoRows`, `selectResultSectionCounts`
- Prior vs Posterior: `selectResultSectionCounts` plus the generated figure asset
- Scenario Explorer: `selectScenarioSnapshots`, `selectResultSectionCounts`
- Model Structure: `selectStructuralProfileRows`, `selectStructuralRunRows`, `selectResultSectionCounts`
- Run Audit & Diagnostics: `selectOverviewStats`, `selectResultSectionCounts`

Payload keys currently used:

- `meta`
- `overview`
- `outcome_context`
- `diagnostics_overview`
- `decision_card`
- `rank_rows`
- `roi_tornado_rows`
- `dollar_tornado_rows`
- `target_channel_detail`
- `quick_overview_lines`
- `recommendations`
- `roi_prior_posterior_table`
- `scenario_items`
- `workbench`
- `structural`
- `how_this_was_run`
- `qc_followup`

## API Connection Map

- App shell: `GET /api/health`; shows `FastAPI reachable` or `Using fallbacks`.
- Upload page: `POST /api/uploads`, then `GET /api/uploads/{upload_id}/profile`; falls back to the Mocha demo profile.
- Review & Start Run: creates a draft workflow and calls `POST /api/workflows/{workflow_id}/config/preview`; falls back to local mock YAML.
- Review & Start Run mock submission: `POST /api/runs`; creates a queued mock run and navigates to `/runs/{run_id}/monitor`.
- Review & Start Run tiny real submission: `POST /api/runs` with `mode: "real_tiny"`; creates a run-specific config and launches the controlled backend subprocess.
- Run Monitor: `GET /api/runs/{run_id}`, `GET /api/runs/{run_id}/logs`, and mock-only `POST /api/runs/{run_id}/mock/advance`; shows queued/running/completed/failed progress.
- Result pages: `GET /api/runs/{run_id}/results/payload`; fall back to the bundled demo payload.
- KPI/revenue, prior grid, and structural settings pages: mock-only configuration scaffolding.

Source labels on connected pages distinguish `API data`, `bundled demo payload`, and `frontend mock data`.

Placeholders that remain:

- Pre-run workflow pages use mock Mocha/demo defaults unless the connected upload/profile or config-preview endpoints respond.
- Run creation is exposed as separate controls: `Start Analysis (Mock)` and guarded `Start Tiny Real Run`.
- Full real run submission, cancellation, and production-scale advisor-grid execution are deferred. Phase 5A only enables the guarded one-run launcher path.

## Mock Run Lifecycle

The product skeleton now supports:

```text
upload/configure -> preview config -> create mock run -> monitor progress -> open completed results
```

The mock run API stores local JSON state and never calls the modeling pipeline.

## Phase 5A Tiny Real Run

On `Review & Start Run`, use `Start Tiny Real Run` only when you intentionally want to prove the end-to-end launcher path. The backend narrows the reviewed config to:

- one target channel
- one `roi_mu` value
- one `roi_sigma` value
- one distribution
- one worker
- output tag `phase5a_tiny_{run_id}`

The backend writes:

- `backend/storage/runs/{run_id}/config.yaml`
- `backend/storage/runs/{run_id}/run.log`

The generated pipeline artifacts are expected under:

- `data/output/01_runs/phase5a_tiny_{run_id}/`
- `data/output/02_tables/phase5a_tiny_{run_id}/`
- `data/output/03_reports/report/phase5a_tiny_{run_id}/`

The Run Monitor polls status and logs. Completed runs show artifact paths and an `Open completed results` link when `dashboard_payload.json` was produced. Failed runs keep the logs visible for inspection. Full 240-run execution remains disabled.

Common failure modes shown in status/logs:

- Dependency/environment issue: missing Python packages or wrong `BLUEALPHA_PIPELINE_PYTHON`.
- Config validation issue: invalid generated YAML, missing columns, or invalid modeling assumptions.
- Pipeline runtime issue: Meridian/model fitting raised during the subprocess.
- Missing output artifact issue: the subprocess finished but expected dashboard/report files were not found.

## Current Execution Status

- Mock mode works and remains separate from real execution.
- `Start Tiny Real Run` works through FastAPI and completed repeatability tests.
- Full 240-run advisor-grid execution is disabled; there is no `Start Full Analysis` UI control.
- Verified successful runs include `run_812a6bbc9bd9`, `run_bfb9120d327a`, `run_31148e5f67db`, and `run_ccf8847b30bc`.
- Intentional failure check: `run_1419024aee3d` failed cleanly and did not expose an `Open completed results` link.
- Completed real-run result pages show `API run data: {run_id}` when loaded from the run payload endpoint.
- Demo routes may still fall back to the bundled demo payload. Real run routes with missing payloads show a payload-unavailable state instead of silently using demo data.
- Known limitation: a one-point tiny run has limited tornado/sensitivity depth because there are no non-baseline grid rows.
- Known limitation: most result page tables/cards are real-run-payload-backed, but the prior-vs-posterior figure asset remains static/demo until run-specific asset serving is added.

Run status fields used by the monitor:

- `run_id`, `workflow_id`, `status`, `created_at`, `started_at`, `completed_at`
- `progress.total_runs`, `progress.completed_runs`, `progress.failed_runs`
- `progress.active_target_channel`, `progress.active_mu`, `progress.active_sigma`, `progress.active_dist`
- `channel_progress[]` with `channel`, `total_runs`, `completedRuns`, `failedRuns`, `status`
- `messages[]`, `monitor_url`, and optional `result_url`

`Advance Mock Progress` moves a stored run through `queued -> running -> completed` by updating local backend storage. It is a testing affordance, not a launcher.

## Current Pre-run Mock State

The Phase 2.6 wizard uses `src/features/workflow/data/mockWorkflow.ts` as a frontend-only draft-analysis stand-in:

- Dataset: `data/raw/monthly_mocha.csv`
- Time column: `date`
- KPI column: `subscriptions`
- KPI type: `non-revenue`
- Revenue assumption: `revenue_per_kpi = 40.0`
- Active channels: `meta`, `google`, `snapchat`, `tiktok`, `moloco`, `liveintent`, `beehiiv`, `amazon`
- Advisor-approved prior grid: 10 mu values × 3 sigma values × `LogNormal`
- Estimated production audit size: `8 × 10 × 3 × 1 = 240 runs`
- Structural assumptions: `alpha_m = 0.3`, `ec_m = 0.5`, `slope_m = 1.2`, `max_lag = 4`
- Sampler/backend placeholders: `n_chains = 4`, `n_adapt = 700`, `n_burnin = 500`, `n_keep = 300`, `seed = 0`, `parallel_workers = 4`

These pages are intentionally pre-run only. They should eventually mutate a draft config/YAML through FastAPI, while post-run pages remain read-only views over completed output payloads.

Future FastAPI fields for the wizard:

- Upload/profile: dataset name/path or upload id, row count, detected columns, validation badges, active/ignored channel columns.
- Config preview: model columns, outcome settings, `revenue_per_kpi`, channel list, prior grid, structural assumptions, sampler settings, estimated run count, and YAML text.
- Real run status: launcher-backed queued/running/completed state, progress by target channel and run number, log/failure summaries, cancellation, and final result artifact locations.

## API Clients

Frontend API clients live in `src/api/`:

- `health.ts`: `GET /api/health`
- `uploads.ts`: `POST /api/uploads`, `GET /api/uploads/{uploadId}/profile`
- `workflows.ts`: draft create/read/update and config preview
- `runs.ts`: create mock run, create tiny real run, read run status, read logs, advance mock progress
- `results.ts`: `GET /api/runs/{run_id}/results/payload`
