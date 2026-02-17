# Marketing Mix Modeling – Prior Sensitivity Analysis
**BlueAlpha Capstone Project 1**

A Bayesian prior sensitivity analysis framework for Marketing Mix Models (MMM).  
This project perturbs prior specifications and measures how sensitive key MMM outputs—such as ROI estimates and channel contributions—are to prior assumptions. The goal is to help analysts and stakeholders understand which conclusions are robust and which depend heavily on modeling choices.

---

## Project Goal

Build a reusable workflow to evaluate how sensitive Bayesian MMM results are to prior assumptions using **Google Meridian**.

In the current implementation, we focus on **ROI prior mean (μ)** sensitivity using the Mocha dataset and report how posterior ROI changes across a grid of μ values.

## Motivation

MMM is widely used to attribute outcomes (e.g., subscriptions or revenue) to marketing channels, but posterior conclusions can depend strongly on prior beliefs—especially when data are limited or channels are correlated.

This project quantifies how changes in priors affect key model outputs, helping teams:
- assess robustness of ROI and channel ranking,
- identify priors that drive major conclusion changes,
- communicate uncertainty and modeling assumptions clearly.

## Current Scope (Base Deliverable)
- Vary **one prior family at a time** (starting with ROI prior mean μ)
- Re-run Meridian for each prior setting (channel × μ grid)
- Compare posterior ROI estimates against a data-calibrated baseline (μ₀)
- Export summary tables (CSV) for downstream plotting and reporting

## Dataset
- `monthly_mocha.csv`: example monthly marketing dataset used for development and testing

## Repository Structure

- `src/`  
  Core Python code for Meridian model fitting and ROI prior sensitivity analysis.
  - `main.py`: orchestrates channel × μ grid runs and aggregates results  
  - `experiment.py`: computes data-calibrated μ0 and builds μ grid from multipliers  
  - `run_meridian_once.py`: runs a single Meridian fit for one (channel, μ)  
  - `utils.py`: shared helper functions (priors/spec building, ROI extraction)

- `data/`  
  Data inputs and generated outputs.
  - `data/raw/`: raw input dataset(s) (e.g., `monthly_mocha.csv`)  
  - `data/output/`: generated result tables (e.g., `prior_sensitivity_results_5mu.csv`)

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
