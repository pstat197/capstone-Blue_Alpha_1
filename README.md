# Marketing Mix Modeling – Prior Sensitivity Analysis
**BlueAlpha Capstone Project 1**

A Bayesian prior sensitivity analysis framework for Marketing Mix Models (MMM) using **Google Meridian**.  
This project perturbs prior specifications and measures how sensitive key MMM outputs—such as ROI estimates and channel contributions—are to prior assumptions. The goal is to help analysts understand which conclusions are robust and which depend heavily on modeling choices.

---

## Project Goal

Build a reusable workflow to evaluate how sensitive Bayesian MMM results are to prior assumptions using **Google Meridian**.

**Current implementation** performs sensitivity analysis on the **ROI prior** for a chosen target channel:
- ROI prior mean **μ**
- ROI prior scale **σ**
- ROI prior distribution family (**Normal** vs **LogNormal**)

The pipeline repeatedly fits Meridian under each prior setting and exports summary results for downstream analysis/plotting.

## Motivation

MMM is widely used to attribute outcomes (e.g., subscriptions or revenue) to marketing channels, but posterior conclusions can depend strongly on prior beliefs—especially when data are limited or channels are correlated.

This project quantifies how changes in priors affect key model outputs, helping teams:
- assess robustness of ROI estimates and channel rankings,
- identify priors that drive major conclusion changes,
- communicate uncertainty and modeling assumptions clearly.

## Current Scope (Base Deliverable)

- Vary one prior family at a time (ROI prior: **μ / σ / dist**)
- Re-run Meridian for each prior setting:
  - `target_channel × μ_grid × σ_grid × dist_grid`
- Build grids around a data-calibrated baseline computed from the dataset
- Export a single aggregated CSV for plotting/reporting
- **Resume-safe**: previously completed runs are skipped automatically

## Dataset

- `data/raw/monthly_mocha.csv`: example monthly marketing dataset used for development and testing

Expected columns:
- KPI: `subscriptions`
- Time: `date` (or `time`)
- For each channel `c`:
  - impressions: `{c}_impressions`
  - spend: `{c}_spend`

Example channels:
`meta, google, snapchat, tiktok, moloco, liveintent, beehiiv, amazon`

## Repository Structure

- `src/`  
  Core Python code for Meridian model fitting and ROI prior sensitivity analysis.
  - `main.py`: orchestrates sensitivity runs & aggregates outputs (resume-safe)
  - `experiment.py`: computes μ0/σ0 and builds μ/σ grids
  - `run_meridian_once.py`: runs one Meridian fit for one `(target_channel, μ, σ, dist)`
  - `utils.py`: shared helpers (build model spec / priors, ROI extraction)
  - `io_utils.py`: I/O helpers (e.g., `normalize_columns()` for backward-compatible results)

- `docs/`  
  Project documentation and deliverables.
  - `docs/reports/`: written reports (PDF)
  - `docs/slides/`: presentation slides / handouts (PDF)
  - `docs/theory/`: theory write-up (LaTeX source + PDF)

- `data/`  
  Data inputs and generated outputs.
  - `data/raw/`: raw input dataset(s) (e.g., `monthly_mocha.csv`)
  - `data/output/`: generated result tables (e.g., `prior_sensitivity_results_meta.csv`)

- `notebooks/`  
  Exploratory notebooks used for development and sanity checks.

- `README.md`  
  Repo-level documentation (this file).

- `requirements.txt`  
  Python dependencies.

## Setup (VSCode + venv)

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```
### MacOS/Linux

```powershell
python3 -m venv .venv 
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```
## Contributors

BlueAlpha Capstone Project 1 Group

- **Jasper Luo** (@JasperLuo0228)
- **Jimmy Wu** (@JimmyWu-312)
- **Coraline Zhu** (@DaixiZhu)
- **Aidan Frazier** (@aidansfrazier)
- **Quinlan Wilson** (@Quinland03)
