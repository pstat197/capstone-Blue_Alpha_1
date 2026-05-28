# Technical Guide

This folder contains the runnable MMM prior-sensitivity code.

## Minimal Flow

```powershell
# 1) End-to-end pipeline (default fixed full-grid sweep)
python -m src.pipeline google meta tiktok --config config/sensitivity.yaml
```

Run mode is controlled from `config/sensitivity.yaml`:

- `run_mode: roi_full` (fixed full ROI grid with the configured production sampler)

## Core Modules

- `main.py`: resolves outcome/prior-design mode, runs fixed full-grid, writes run/ROI outputs.
- `run_meridian_once.py`: one model fit + diagnostics + ROI extraction (includes ModelSpec building).
- `summarize_sensitivity.py`: merges split outputs, writes the tornado table consumed by the React payload.
- `pipeline.py`: one-command orchestrator for fixed full-grid workflow.
- `formatting.py`: shared formatting, value-safety, and QC status helpers.
- `reporting/make_dashboard.py`: builds the React dashboard payload and supporting tables.
- `viz/tornado_plots.py`, `viz/roi_prior_vs_posterior.py`: optional manual research/export utilities, not part of the default React runtime.

## Input Contract (minimum)

- time column (`date` or configured `model.time_col`)
- KPI column (`outcome.kpi_col` / legacy `model.kpi_col`)
- for each channel `c`:
  - `{c}_impressions`
  - `{c}_spend`

## Output Contract

For tag `<tag>`:

- `data/output/01_runs/<tag>/prior_sensitivity_runs_multi_<tag>.csv`
- `data/output/01_runs/<tag>/prior_sensitivity_roi_multi_<tag>.csv`
- `data/output/02_tables/<tag>/tornado_<tag>.csv`
- `data/output/03_reports/report/<tag>/tables/dashboard_payload.json`

Default workflow is fixed full-grid sweep (`sweep.type: fixed_full_grid`).

`LogNormal` prior parameterization note:

- `roi_mu` / `roi_sigma` are treated as natural-scale mean and std targets.
- Code converts them to log-space parameters before creating `tfd.LogNormal(...)`.

## Troubleshooting

- `Configured data CSV does not exist`  
  Fix `model.data_csv` in YAML.

- `Permission denied` while writing outputs  
  Close the HTML/CSV file in browser/Excel, then rerun.

- Extremely large `%` changes  
  Often near-zero baseline ROI; check `Delta ROI` and stability flags.
