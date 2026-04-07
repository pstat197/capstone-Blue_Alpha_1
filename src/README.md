# Meridian Prior Sensitivity Code

This folder contains the runnable code for BlueAlpha Capstone Project 1:
Bayesian MMM prior-sensitivity analysis with Google Meridian.

## Quickstart

Run from repo root.

1. End-to-end pipeline (recommended)

```powershell
python -m src.pipeline google meta tiktok --config config/sensitivity_google_meta_tiktok_full18.yaml
```

2. Build merged summary table (if needed separately)

```powershell
python -m src.summarize_sensitivity google meta tiktok
```

3. Build client report + interactive dashboard

```powershell
python -m src.reporting.make_report --input data/output/02_tables/google_meta_tiktok/prior_sensitivity_report_input_google_meta_tiktok.csv --outdir data/output/03_reports/report/google_meta_tiktok --clean-output
```

Outputs from step 3:
- `report.html`
- `dashboard.html`
- `tables/dashboard_payload.json`

## What This Pipeline Does

For a target set (for example `google meta tiktok`), we run many MMM fits while varying ROI prior assumptions:
- `roi_prior_mu`
- `roi_prior_sigma`
- `roi_prior_dist` (`Normal` / `LogNormal`)

Then we compare each run to a baseline run and quantify sensitivity:
- absolute ROI delta
- percent ROI change
- optional value/dollar impact columns

## Core Scripts

- `src/main.py`
  - runs sensitivity experiments
  - writes split run-level outputs under `data/output/01_runs/<tag>/`

- `src/run_meridian_once.py`
  - fits one Meridian model for one parameter tuple
  - writes one run diagnostics row + per-channel ROI rows

- `src/summarize_sensitivity.py`
  - merges split runs/ROI by `run_id`
  - writes `data/output/02_tables/<tag>/tornado_<tag>.csv`

- `src/recommend_next_grid.py`
  - consumes tornado summary and suggests next tests
  - excludes `FAIL` runs from candidates

- `src/next_grid_generator.py`
  - writes a next-iteration YAML config from QC outcomes
  - updates `defaults.targets`, `experiment.roi_mu_values`, `experiment.roi_sigma_values`, `experiment.roi_dist_values`

- `src/viz/tornado_plots.py`
  - builds tornado visual outputs from `tornado_<tag>.csv`

- `src/reporting/make_report.py`
  - builds integrated HTML report and dashboard

- `src/pipeline.py`
  - one-command orchestrator:
  - `main -> summarize -> tornado plots -> report`

## Common Commands

### A) Run sensitivity only

```powershell
python -m src.main --targets google meta tiktok --config config/sensitivity_google_meta_tiktok_full18.yaml
```

### B) Summarize tornado table

```powershell
python -m src.summarize_sensitivity google meta tiktok
```

### C) Recommend next grid

```powershell
python -m src.recommend_next_grid google meta tiktok
```

### D) Generate next YAML directly

```powershell
python -m src.next_grid_generator google meta tiktok --config-in config/sensitivity_google_meta_tiktok_full18.yaml --config-out config/sensitivity_google_meta_tiktok_next.yaml
python -m src.main --config config/sensitivity_google_meta_tiktok_next.yaml
```

### E) Build report/dashboard

```powershell
python -m src.reporting.make_report --input data/output/02_tables/google_meta_tiktok/prior_sensitivity_report_input_google_meta_tiktok.csv --outdir data/output/03_reports/report/google_meta_tiktok --clean-output
```

### F) Full pipeline (recommended)

```powershell
python -m src.pipeline google meta tiktok --config config/sensitivity_google_meta_tiktok_full18.yaml
```

## Input Data Contract

Minimum columns expected:
- time column: `date` (or configured `model.time_col`)
- KPI column: configured `model.kpi_col`
- for each channel `c`:
  - `{c}_impressions`
  - `{c}_spend`

Optional geo-level fields:
- `model.geo_col` (for geo MMM)
- `model.population_col` (recommended with geo)

Example channels:
- `google, meta, tiktok, snapchat, moloco, liveintent, beehiiv, amazon`

## Output Data Contract

For target tag `<tag>` (sorted underscore-joined targets):

- Runs CSV:
  - `data/output/01_runs/<tag>/prior_sensitivity_runs_multi_<tag>.csv`
- ROI CSV:
  - `data/output/01_runs/<tag>/prior_sensitivity_roi_multi_<tag>.csv`
- Tornado CSV:
  - `data/output/02_tables/<tag>/tornado_<tag>.csv`
- Report input CSV:
  - `data/output/02_tables/<tag>/prior_sensitivity_report_input_<tag>.csv`
- Final report folder:
  - `data/output/03_reports/report/<tag>/`

## Baseline and Grid Behavior

- If `experiment.roi_mu_values` is provided in YAML, those values are used directly.
- Otherwise, `mu_grid` is built from baseline `mu0 * multipliers`.
- If `experiment.roi_sigma_values` is provided in YAML, those values are used directly.
- Otherwise, `sigma_grid` is built from baseline `sigma0 * multipliers`.
- Distribution set is controlled by `experiment.roi_dist_values`.

Baseline run selection:
- default baseline is selected from active grid (nearest baseline values)
- optional manual override:
  - `baseline.roi_mu`
  - `baseline.roi_sigma`
  - `baseline.roi_dist`
- manual baseline values must exist in active grid

## QC Interpretation (Short)

Run diagnostics come from Meridian reviewer checks and are rolled up into:
- `PASS`
- `REVIEW`
- `FAIL`

Useful columns:
- `qc_status_code`
- `qc_summary_short`
- `qc_primary_review_check`
- `qc_flagged_channels`

Common examples:
- `REVIEW:PriorPosteriorShift`: usable but needs review
- `FAIL:Baseline`: baseline decomposition not reliable for decision use

## Geo-Level Note

If you run with a geo config but your dataset has no valid geo column, the run behaves like national-level sensitivity.
That run is still useful for prior sensitivity benchmarking, but it is not a true geo MMM experiment.

## Troubleshooting

- `Configured data CSV does not exist`
  - fix `model.data_csv` in YAML or place the file at expected path

- `Permission denied` writing report outputs
  - close open HTML/CSV files in browser/Excel
  - rerun command

- Extremely large percent changes
  - often caused by very small or negative baseline ROI denominators
  - use absolute delta ROI and stability flags alongside percent ranking

## Related Docs

- root README: project-level overview and repo layout
- `docs/dashboard_productization_notes.md`: dashboard architecture notes
