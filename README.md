# Marketing Mix Modeling - Prior Sensitivity Analysis
**BlueAlpha Capstone Project 1**

Bayesian prior sensitivity analysis for Marketing Mix Models (MMM) using **Google Meridian**.
This project perturbs ROI priors and measures how model conclusions move under different assumptions.

## Project Goal

Build a reusable workflow to evaluate prior sensitivity in Meridian and produce stable expanded-stage outputs:

- split run diagnostics CSV
- split per-channel ROI CSV
- tornado-ready summary CSV
- recommendation summary for next-grid testing

## Current Workflow

The current pipeline supports:

- single-target sensitivity (`--channels`)
- linked multi-prior sensitivity (`--targets`)
- post-fit quality checks (`PASS`, `REVIEW`, `FAIL`)
- tornado output with QC and impact columns
- recommendation stage (`src.recommend_next_grid`) for next-iteration planning

Core scripts:

- `src/main.py`
  - orchestrates sensitivity runs
  - writes split outputs under `data/output/01_runs/<tag>/`:
    - `prior_sensitivity_runs_multi_<tag>.csv`
    - `prior_sensitivity_roi_multi_<tag>.csv`
- `src/run_meridian_once.py`
  - fits one model
  - runs model reviewer checks
  - writes one run diagnostics row and per-channel ROI rows
- `src/summarize_sensitivity.py`
  - merges split run/ROI outputs by `run_id`
  - writes `data/output/02_tables/<tag>/tornado_<tag>.csv`
  - supports value columns with `--dps` / `--dollars_per_subscription` (default `100`)
- `src/recommend_next_grid.py`
  - reads tornado output
  - excludes `FAIL` runs
  - prints best stable and aggressive next tests
  - summarizes flagged channel frequency
- `src/viz/tornado_plots.py`
  - builds tornado dollar-sensitivity plots/reports from `data/output/02_tables/*/tornado_*.csv`
- `src/reporting/make_report.py`
  - builds an HTML summary report from merged sensitivity results
  - includes diagnostics summary if `qc_*` columns exist in report input
  - includes ROI tornado (% units) and dollar tornado ($ units)
  - dollar tornado matches `src.viz.tornado_plots` channel-level interval style
  - supports co-branding logos/label from `config/report_config.yaml` `branding` section
  - includes one selected-run channel snapshot (single scenario tornado) for side-by-side channel comparison
  - displays exact source files used in report header (report input / tornado / runs / roi)
  - uses `config/report_config.yaml`
- `src/pipeline.py`
  - one-command orchestration for run -> summarize -> tornado plot -> auto report

Detailed operating docs are in:

- `src/README.md`

## Dataset

The pipeline supports any tabular dataset (CSV) not just Mocha.
- `data/raw/monthly_mocha.csv`

Expected columns:

- KPI column (e.g., `revenue`, `subscriptions`, `units_sold`)
- time: `date` (or `time`)
- for each channel `c`:
  - `{c}_impressions`
  - `{c}_spend`

Flexible KPI Handling:

- If a revenue-like column is detected(revenue, rev, total_revenue), it is used automatically.
- Otherwise the user is prompted to:
  - select a KPI column (e.g., `subscriptions`, `units_sold`)
  - provide a multiplier to convert KPI to revenue
  - a new revenue column is created for sensitivity analysis (e.g., `subscriptions_as_revenue`)

Expected Channels:

- Spend columns should be named `{channel}_spend` (e.g., `google_spend`, `meta_spend`, `moloco_spend`)
- Impression columns should be named `{channel}_impressions` (e.g., `google_impressions`, `meta_impressions`, `moloco_impressions`)

## Common Commands

Run from repo root.

Run full end-to-end pipeline (recommended):

```powershell
python -m src.pipeline google meta moloco
```

Run expanded linked sensitivity:

```powershell
python -m src.main --targets google meta moloco
```

Generate tornado summary:

```powershell
python -m src.summarize_sensitivity google meta moloco
```

Generate recommendation summary:

```powershell
python -m src.recommend_next_grid google meta moloco
```

Generate tornado sensitivity visualization reports:

```powershell
python -m src.viz.tornado_plots --input-mode single --csv data/output/02_tables/google_meta_moloco/tornado_google_meta_moloco.csv --outdir data/output/03_reports/tornado_outputs/google_meta_moloco
```

Generate auto HTML report:

```powershell
python -m src.reporting.make_report --input data/output/02_tables/google_meta_moloco/prior_sensitivity_report_input_google_meta_moloco.csv --outdir data/output/03_reports/report/google_meta_moloco
python -m src.reporting.make_report --input data/output/02_tables/google_meta_tiktok/prior_sensitivity_report_input_google_meta_tiktok.csv --outdir data/output/03_reports/report/google_meta_tiktok --clean-output
```

## Repository Structure

- `src/` core pipeline and analysis code
- `src/reporting/` auto-report generation modules and templates
- `data/raw/` source data
- `data/output/01_runs/` raw run outputs (`runs/roi`)
- `data/output/02_tables/` derived tables (`tornado`, report inputs)
- `data/output/03_reports/` final PNG/HTML artifacts
- `config/` sensitivity/report configuration files
- `docs/` reports, slides, and generated artifacts
- `notebooks/` exploratory notebooks
- `requirements.txt` Python dependencies

## Contributors

BlueAlpha Capstone Project 1 Group

- **Jasper Luo** (@JasperLuo0228)
- **Jimmy Wu** (@JimmyWu-312)
- **Coraline Zhu** (@DaixiZhu)
- **Aidan Frazier** (@aidansfrazier)
- **Quinlan Wilson** (@Quinland03)
