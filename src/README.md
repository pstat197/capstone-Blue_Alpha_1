# Technical Guide

This folder contains the runnable MMM prior-sensitivity code.

## Minimal Flow

```powershell
# 1) End-to-end pipeline (always two-layer)
python -m src.pipeline google meta tiktok --config config/sensitivity.yaml
```

## Core Modules

- `main.py`: runs experiment grid (includes experiment config + baseline stats).
- `run_meridian_once.py`: one model fit + diagnostics + ROI extraction (includes ModelSpec building).
- `summarize_sensitivity.py`: merges split outputs, writes tornado table.
- `pipeline.py`: one-command orchestrator.
- `formatting.py`: shared formatting, value-safety, and QC status helpers.
- `reporting/make_dashboard.py`: builds dashboard artifacts (includes CSV loading).
- `viz/tornado_plots.py`: tornado sensitivity visualizations.

## Input Contract (minimum)

- time column (`date` or configured `model.time_col`)
- KPI column (`model.kpi_col`)
- for each channel `c`:
  - `{c}_impressions`
  - `{c}_spend`

## Output Contract

For tag `<tag>`:

- `data/output/01_runs/<tag>/prior_sensitivity_runs_multi_<tag>.csv`
- `data/output/01_runs/<tag>/prior_sensitivity_roi_multi_<tag>.csv`
- `data/output/02_tables/<tag>/tornado_<tag>.csv`
- `data/output/03_reports/report/<tag>/dashboard.html`

Two-layer mode keeps dashboard inputs clean by removing Layer 1 artifacts before Layer 2 final run.

## Troubleshooting

- `Configured data CSV does not exist`  
  Fix `model.data_csv` in YAML.

- `Permission denied` while writing outputs  
  Close the HTML/CSV file in browser/Excel, then rerun.

- Extremely large `%` changes  
  Often near-zero baseline ROI; check `Delta ROI` and stability flags.



