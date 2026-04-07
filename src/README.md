# src/ Technical Guide

This folder contains the runnable MMM prior-sensitivity code.

## Minimal Flow

```powershell
# 1) Run sensitivity experiments
python -m src.main --targets google meta tiktok --config config/sensitivity_google_meta_tiktok_full18.yaml

# 2) Build tornado summary table
python -m src.summarize_sensitivity google meta tiktok

# 3) Build dashboard package
python -m src.reporting.make_report --input data/output/02_tables/google_meta_tiktok/prior_sensitivity_report_input_google_meta_tiktok.csv --outdir data/output/03_reports/report/google_meta_tiktok --clean-output
```

## Core Modules

- `main.py`: runs experiment grid and writes split run outputs.
- `run_meridian_once.py`: one model fit + diagnostics row + ROI rows.
- `summarize_sensitivity.py`: merges split outputs, writes tornado table.
- `recommend_next_grid.py`: suggests next tests from sensitivity + QC.
- `next_grid_generator.py`: writes next-iteration YAML automatically.
- `pipeline.py`: one-command orchestrator.
- `reporting/make_report.py`: builds dashboard/report artifacts.

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

## Troubleshooting

- `Configured data CSV does not exist`  
  Fix `model.data_csv` in YAML.

- `Permission denied` while writing outputs  
  Close the HTML/CSV file in browser/Excel, then rerun.

- Extremely large `%` changes  
  Often near-zero baseline ROI; check `Delta ROI` and stability flags.



