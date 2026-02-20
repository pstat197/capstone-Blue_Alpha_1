# Meridian Prior Sensitivity Code

This folder contains runnable scripts for fitting Meridian MMM models and running a prior sensitivity analysis on the ROI prior parameters using the Mocha dataset.

We run sensitivity over:
- ROI prior mean **μ**
- ROI prior scale **σ**
- ROI prior distribution (**Normal** vs **LogNormal**)

The model can include all channels, but we can choose to only run sensitivity for a single **target channel** (e.g., `meta`) to reduce compute.

---

## Table of Contents

- [Overview](#overview)
- [Repo Layout](#repo-layout)
- [Inputs and Naming Conventions](#inputs-and-naming-conventions)
- [How the Pipeline Works](#how-the-pipeline-works)
- [ROI Prior Grids (μ and σ)](#roi-prior-grids-μ-and-σ)
- [How to Run](#how-to-run)
- [Outputs](#outputs)
- [Notes / Common Issues](#notes--common-issues)

## Overview

- **Goal:** Evaluate how sensitive Meridian ROI estimates are to assumptions about the ROI prior (**μ**, **σ**, and distribution).
- **Dataset:** `data/raw/monthly_mocha.csv` (subscriptions KPI + channel media variables).
- **Approach:** Construct data-calibrated baseline priors from the dataset, generate multiplicative grids, and run Meridian repeatedly while varying priors for a target channel.

---

## Repo Layout

- `src/main.py`  
  Orchestrates the experiment. Loops over:
  - `target_channels_to_run` (default `["meta"]`)
  - `roi_mu_values` grid
  - `roi_sigma_values` grid
  - `roi_dist_values` grid  
  Calls `run_meridian_once.py` as a subprocess and appends results into one CSV.

- `src/experiment.py`  
  Centralizes experiment configuration and grid construction:
  - loads `data/raw/monthly_mocha.csv`
  - validates spend columns exist: `{channel}_spend`
  - computes baseline:
    - `μ0 = median(subscriptions / total_spend)`
    - `σ0 = std(subscriptions / total_spend)`
  - builds sensitivity grids using multipliers:
    - `μ_grid = μ0 × multipliers`
    - `σ_grid = σ0 × multipliers`
  - defines ROI prior distributions:
    - `["Normal", "LogNormal"]` by default

- `src/run_meridian_once.py`  
  Fits one Meridian model given:
  - full channel list (for model media inputs)
  - a chosen `target_channel`
  - ROI prior (`μ`, `σ`, `dist`) for that target channel  
  Writes a run-level ROI summary to a temporary CSV that `main.py` appends to the master results file.

- `src/utils.py`  
  Model helpers:
  - `build_model_spec(...)` (injects the ROI prior for the target channel)
  - `extract_roi_mean(...)` (extracts ROI summaries from the fitted model)

- `src/io_utils.py`  
  I/O utilities:
  - `normalize_columns(df)` to make result CSVs backward compatible (e.g., `prior_sigma` → `roi_prior_sigma`).

---

## Inputs and Naming Conventions

The pipeline assumes the dataset includes:
- KPI column: `subscriptions`
- Time column: `date` (will be renamed to `time`) or `time`
- For each channel `c`:
  - impressions: `{c}_impressions`
  - spend: `{c}_spend`

Example channels:
`meta, google, snapchat, tiktok, moloco, liveintent, beehiiv, amazon`

---

## How the Pipeline Works

1. `experiment.py` loads `data/raw/monthly_mocha.csv` and builds an `ExperimentConfig`:
   - spend columns: `{channel}_spend`
   - total spend per row: `total_spend = sum(spend_cols)`
   - baseline ROI ratio per row: `roi_row = subscriptions / total_spend`
   - baseline center:
     - `μ0 = median(roi_row)`
     - `σ0 = std(roi_row)`
   - grids:
     - `μ_grid = μ0 × {0.4, 0.7, 1.0, 1.4, 2.0}`
     - `σ_grid = σ0 × {0.4, 0.7, 1.0, 1.4, 2.0}`
   - dists:
     - `dist_grid = ["Normal", "LogNormal"]`

2. `main.py` chooses which target channels to run sensitivity for:
   - default: `target_channels_to_run = ["meta"]`
   - the model still includes **all channels** as media inputs, but the ROI prior is modified only for the chosen target.

3. For each `(target_channel, μ, σ, dist)` combination:
   - `main.py` calls `run_meridian_once.py` in a subprocess
   - the subprocess fits a Meridian model and writes a temporary output CSV

4. `main.py` appends that temporary output into the master results file and deletes the temp file.

5. Resume behavior:
   - If the master results CSV already exists, `main.py` loads it, normalizes column names, and skips combinations already completed.
---

## ROI Prior Grids (μ and σ)

We interpret ROI on the natural scale:

`ROI ≈ incremental_subscriptions / spend`  (subscriptions per dollar)

### Baseline calibration from the dataset
We compute a weakly-informative baseline centered on observed scale:

- `μ0 = median(subscriptions / total_spend)`
- `σ0 = std(subscriptions / total_spend)`

This does not claim causality; it anchors priors to a realistic order of magnitude so sensitivity experiments are meaningful.

### Multiplicative sensitivity (default 5 points)
We vary both μ and σ by multiplicative factors:

`multipliers = {0.4, 0.7, 1.0, 1.4, 2.0}`

So:

- `μ ∈ μ0 × multipliers`
- `σ ∈ σ0 × multipliers`

### Distribution sensitivity
We also test the ROI prior distribution family:

- `dist ∈ {"Normal", "LogNormal"}`

---


