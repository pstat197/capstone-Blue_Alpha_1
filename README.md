# BlueAlpha Capstone 1: MMM Prior Sensitivity

Bayesian prior-sensitivity workflow for Google Meridian MMM.  
We perturb ROI priors (`mu`, `sigma`, `dist`) and evaluate how conclusions move under different assumptions.

[![Try Demo - Local](https://img.shields.io/badge/Try%20Demo-Local%20Private%20Repo-2f5dc6?style=for-the-badge)](#run-demo-private-repo-safe)
[![Open Data Contract](https://img.shields.io/badge/Open-dashboard_payload.json-475569?style=for-the-badge)](data/output/03_reports/report/google_meta_tiktok/tables/dashboard_payload.json)

Private repo note: external HTML hosts (for example `raw.githack`) may return 404 for private content.  
Use the local demo launcher below.

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
python -m src.reporting.make_dashboard --input data/output/02_tables/google_meta_tiktok/prior_sensitivity_report_input_google_meta_tiktok.csv --outdir data/output/03_reports/report/google_meta_tiktok --clean-output
```

Open:

- `data/output/03_reports/report/google_meta_tiktok/dashboard.html`

## Run Demo (Private Repo Safe)

Default example target: `google_meta_tiktok`

```powershell
powershell -ExecutionPolicy Bypass -File scripts/open_demo.ps1
```

Optional custom tag/port:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/open_demo.ps1 -Tag google_meta_moloco -Port 8766
```

## Output You Can Share

For a target tag `<tag>` (example: `google_meta_tiktok`):

- Runs CSV: `data/output/01_runs/<tag>/prior_sensitivity_runs_multi_<tag>.csv`
- ROI CSV: `data/output/01_runs/<tag>/prior_sensitivity_roi_multi_<tag>.csv`
- Tornado CSV: `data/output/02_tables/<tag>/tornado_<tag>.csv`
- Dashboard folder: `data/output/03_reports/report/<tag>/`
- Meridian official embeds (when baseline run is executed): `data/output/03_reports/report/<tag>/figures/meridian_official/`

## Main Commands

```powershell
# Sensitivity run only
python -m src.main --targets google meta tiktok --config config/sensitivity_google_meta_tiktok_full18.yaml

# Build merged sensitivity table
python -m src.summarize_sensitivity google meta tiktok

# Recommend next grid
python -m src.recommend_next_grid google meta tiktok

# Build dashboard
python -m src.reporting.make_dashboard --input data/output/02_tables/google_meta_tiktok/prior_sensitivity_report_input_google_meta_tiktok.csv --outdir data/output/03_reports/report/google_meta_tiktok --clean-output
```

### Meridian Official Outputs (Health Card + 6 Standard Charts)

`src.main` now exports Meridian official HTML assets from the baseline grid point into:

- `data/output/03_reports/report/<tag>/figures/meridian_official/`

The dashboard auto-detects and renders these six Meridian standard charts:

- `spend_vs_contribution`
- `roi_by_channel`
- `roi_vs_mroi`
- `roi_vs_effectiveness`
- `contribution_waterfall`
- `contribution_over_time`

Model Health Card is rendered inline in the dashboard from `manifest.json` (`health_card_data`) and no longer requires `health_card.html`.
Official charts are rendered directly in dashboard cards (no iframe container).

If files are missing, the QC section shows a placeholder message instead of failing.

## Repo Map

```
BLUEALPHA/
  config/          sensitivity + report YAML configs
  data/
    raw/           input CSVs (mocha, geo, test)
    output/
      01_runs/     raw Meridian run outputs per channel group
      02_tables/   merged sensitivity tables, tornado CSVs
      03_reports/  client-facing HTML dashboards, figures, tables
  docs/            theory, slides, interim reports, project management
  notebooks/       Jupyter notebooks (Colab prior-sensitivity, visualization)
  scripts/         utility scripts (demo launcher)
  src/
    main.py              grid orchestrator + experiment config + baseline stats
    run_meridian_once.py single Meridian fit + QC + ROI + ModelSpec building
    pipeline.py          one-command end-to-end runner with skip flags
    summarize_sensitivity.py  post-run merge, baseline detection, tornado table
    run_config.py        YAML config loading, defaults, validation
    io_utils.py          CSV I/O, resume logic, column normalization
    output_paths.py      centralized output path management
    formatting.py        shared formatting and value-safety helpers
    recommend_next_grid.py  data-driven next-grid recommendations
    reporting/           dashboard + report generation (metrics, figures, render)
    viz/                 tornado plots
```

### Pipeline flow

```
config/*.yaml  -->  src/main.py  --(subprocess)-->  src/run_meridian_once.py
                                                        |
                    src/summarize_sensitivity.py  <------+  (merge CSVs)
                                |
                +---------------+---------------+
                |                               |
        src/viz/tornado_plots.py    src/reporting/make_dashboard.py
                                        |-- metrics.py
                                        |-- figures.py
                                        +-- render.py --> HTML dashboard
```

## Input Data (`data/raw/`)

| File | Rows | Description |
|------|-----:|-------------|
| `monthly_mocha.csv` | 73 | Primary national-level dataset (8 channels, KPI = subscriptions) |
| `monthly_mocha_geo.csv` | 74 | Same dataset with `state` + `population` columns for geo-level runs |
| `new_data.csv` | 24 | Alternate dataset (same channels, different time range) |
| `new_data_with_revenue.csv` | 24 | `new_data` with a revenue KPI column |
| `test_data.csv` | 5 | Toy dataset for smoke tests (4 channels: pinterest, reddit, linkedin, tv) |
| `test_data_with_revenue.csv` | 6 | `test_data` with a revenue KPI column |

## Config Files (`config/`)

| File | Purpose |
|------|---------|
| `sensitivity_geo_template.yaml` | Full 8-channel geo-level template (reference starting point) |
| `sensitivity_google_meta_tiktok_full18.yaml` | 3-channel production config |
| `sensitivity_google_meta_tiktok_qc_next.yaml` | Auto-generated config from `recommend_next_grid` |
| `sensitivity_google_meta_tiktok_qc_strict.yaml` | Stricter QC variant (Normal-only, higher thresholds) |
| `report_google_meta_tiktok.yaml` | Report/dashboard generation config (branding, thresholds, figure flags) |

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
