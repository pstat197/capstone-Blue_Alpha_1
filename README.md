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
  - writes split outputs:
    - `prior_sensitivity_runs_*.csv`
    - `prior_sensitivity_roi_*.csv`
- `src/run_meridian_once.py`
  - fits one model
  - runs model reviewer checks
  - writes one run diagnostics row and per-channel ROI rows
- `src/summarize_sensitivity.py`
  - merges split run/ROI outputs by `run_id`
  - writes `tornado_<tag>.csv`
  - supports value columns with `--dps` / `--dollars_per_subscription` (default `100`)
- `src/recommend_next_grid.py`
  - reads tornado output
  - excludes `FAIL` runs
  - prints best stable and aggressive next tests
  - summarizes flagged channel frequency

Detailed operating docs are in:

- `src/README.md`

## Dataset

- `data/raw/monthly_mocha.csv`

Expected columns:

- KPI: `subscriptions`
- time: `date` (or `time`)
- for each channel `c`:
  - `{c}_impressions`
  - `{c}_spend`

Default channel list:

- `meta, google, snapchat, tiktok, moloco, liveintent, beehiiv, amazon`

## Common Commands

Run from repo root.

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

## Repository Structure

- `src/` core pipeline and analysis code
- `data/raw/` source data
- `data/output/` generated CSV outputs
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
