# BlueAlpha Capstone 1: MMM Prior Sensitivity

Bayesian prior-sensitivity workflow for Google Meridian MMM.  
We perturb ROI priors (`mu`, `sigma`, `dist`) and evaluate how conclusions move under different assumptions.

[![Try Demo - Dashboard](https://img.shields.io/badge/Try%20Demo-Dashboard-2f5dc6?style=for-the-badge)](data/output/03_reports/report/google_meta_tiktok/dashboard.html)
[![Open Data Contract](https://img.shields.io/badge/Open-dashboard_payload.json-475569?style=for-the-badge)](data/output/03_reports/report/google_meta_tiktok/tables/dashboard_payload.json)

If GitHub opens HTML as source text, download the folder and open `dashboard.html` locally.

## What This Project Delivers

- End-to-end prior sensitivity runs for MMM.
- QC tagging at run level (`PASS` / `REVIEW` / `FAIL`).
- Sensitivity tables (ROI % and Delta ROI).
- Client-facing interactive dashboard HTML output.
- Next-grid recommendations for reruns.

## Quickstart

From repo root:

```powershell
# 1) Run pipeline
python -m src.pipeline google meta tiktok --config config/sensitivity_google_meta_tiktok_full18.yaml

# 2) Build dashboard package
python -m src.reporting.make_report --input data/output/02_tables/google_meta_tiktok/prior_sensitivity_report_input_google_meta_tiktok.csv --outdir data/output/03_reports/report/google_meta_tiktok --clean-output
```

Open:

- `data/output/03_reports/report/google_meta_tiktok/dashboard.html`

## Output You Can Share

For a target tag `<tag>` (example: `google_meta_tiktok`):

- Runs CSV: `data/output/01_runs/<tag>/prior_sensitivity_runs_multi_<tag>.csv`
- ROI CSV: `data/output/01_runs/<tag>/prior_sensitivity_roi_multi_<tag>.csv`
- Tornado CSV: `data/output/02_tables/<tag>/tornado_<tag>.csv`
- Dashboard folder: `data/output/03_reports/report/<tag>/`

## Main Commands

```powershell
# Sensitivity run only
python -m src.main --targets google meta tiktok --config config/sensitivity_google_meta_tiktok_full18.yaml

# Build merged sensitivity table
python -m src.summarize_sensitivity google meta tiktok

# Recommend next grid
python -m src.recommend_next_grid google meta tiktok

# Build dashboard
python -m src.reporting.make_report --input data/output/02_tables/google_meta_tiktok/prior_sensitivity_report_input_google_meta_tiktok.csv --outdir data/output/03_reports/report/google_meta_tiktok --clean-output
```

## Repo Map

- `src/` core analysis pipeline
- `src/reporting/` dashboard/report generation
- `config/` experiment and report configs
- `data/raw/` input data
- `data/output/` generated run/table/report artifacts
- `docs/` notes and productization docs

## Geo-Level Note

If dataset has no valid geo column, run is treated as national-level sensitivity.  
This is still useful for prior robustness, but not a true geo MMM experiment.

## Team

BlueAlpha Capstone Project 1 Group

- Jasper Luo
- Jimmy Wu
- Coraline Zhu
- Aidan Frazier
- Quinlan Wilson


