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
- [Tornado Ready Summary Table](#tornado-ready-summary-table)
- [Visualization](#visualization)

## Overview

- **Goal:** Evaluate how sensitive Meridian ROI estimates are to assumptions about the ROI prior (**μ**, **σ**, and distribution).
- **Dataset:** `data/raw/monthly_mocha.csv` (subscriptions KPI + channel media variables).
- **Approach:** Construct data-calibrated baseline priors from the dataset, generate multiplicative grids, and run Meridian repeatedly while varying priors for a target channel.

---

## Repo Layout

- `src/main.py`  
  Orchestrates the sensitivity experiment and supports two run modes:

  **Single-target mode (Base):**
  - target channels provided via CLI: `--channels` (e.g., `tiktok`, `meta google`, or `all`)
  - loops over `roi_mu_values`, `roi_sigma_values`, `roi_dist_values`

  **Multi-prior mode (Expanded, linked):**
  - target channels provided via CLI: `--targets` (e.g., `meta tiktok`)
  - applies the same `(μ, σ, dist)` to *all targets simultaneously* by passing a JSON overrides dict
    via `--roi_prior_overrides_json` (linked scenario)

  **Baseline parameters (passed to every run):**
  - `baseline_mu = cfg.mu0`
  - `baseline_sigma = cfg.roi_sigma_values[0]`
  - `baseline_dist = "LogNormal"`

  Calls `run_meridian_once.py` as a subprocess and appends each run’s temporary CSV into a master
  results file (resume-safe).

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
  Fits one Meridian model for a single prior setting and writes a run-level ROI output CSV.

  **Inputs / modes:**
  - Uses the full `channels` list to build media inputs (`{channel}_impressions`, `{channel}_spend`) for the model.
  - **Single-target mode:** called with `--target_channel --mu --sigma --dist` to modify the ROI prior for one target channel.
  - **Multi-prior (linked) mode:** called with `--roi_prior_overrides_json`, a JSON dict mapping each target channel to a prior spec
    (typically the same `{"mu": ..., "sigma": ..., "dist": ...}` applied to all targets in that run).

  The resulting temporary CSV is later appended into the master results file by `main.py`.

- `src/summarize_sensitivity.py`  
  Generates a tornado-ready summary table for a target set (pair / triple / etc.). It accepts targets as positional CLI args
  (e.g., `python -m src.summarize_sensitivity meta tiktok`).

  - automatically locates the input results CSV:
    - `data/output/prior_sensitivity_results_multi_<tag>.csv`
  - if the input file does not exist, it will first run:
    - `python -m src.main --targets <targets...>`
    to generate the results
  - identifies baseline using `is_baseline == True`
  - computes:
    - `delta_abs = |roi_new - roi_baseline|`
    - `delta_pct = |roi_new/roi_baseline - 1|`
  - exports `data/output/tornado_<tag>.csv` with columns:
    `targets, prior_key, channel, roi_baseline, roi_new, delta_abs, delta_pct`

- `src/utils.py`  
  Model helpers:
  - `build_model_spec(...)` injects ROI priors for either:
    - a single target channel, or
    - multiple target channels via an overrides dict (multi-prior)
  - `extract_roi_mean(...)` extracts ROI summaries from the fitted model

- `src/io_utils.py`  
  I/O + CLI utilities:
  - `normalize_columns(df)` to make result CSVs backward compatible (e.g., `prior_sigma` → `roi_prior_sigma`)
  - `parse_channels_and_output(...)` parses:
    - `--channels` for single-target mode
    - `--targets` for linked multi-prior mode
    and auto-creates the sensitivity output filename
  - `load_resume_state(...)` loads existing results and builds a resume-safe “already done” set
  - `append_tmp_to_output(...)` appends run-level temporary outputs into the master results CSV

- `src/viz/`  
  Visualization utilities for sensitivity results:
  - `src/viz/prior_viz.py` merges per-channel result CSVs and generates summary plots:
    - basic ROI plots (histogram + scatter vs μ/σ)
    - prior sensitivity heatmap
    - prior sensitivity ranking
  - The merged CSV is saved to: `data/output/prior_sensitivity_results_all_channels.csv`
  - Figures are saved under `docs/figures/roi/` by default (`basic/`, `heatmap/`, `sensitivity_ranking/`).
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

2. `main.py` chooses the run mode via CLI:

   **Single-target mode (Base):**
   - example usage: `python -m src.main --channels tiktok`
   - all channels: `python -m src.main --channels all`

   The model still includes **all channels** as media inputs, but the ROI prior is modified only for the chosen target channel(s).
   The output file name is automatically generated based on `--channels`.

   **Multi-prior mode (Expanded, linked):**
   - example usage: `python -m src.main --targets meta tiktok`

   In this mode, the same `(μ, σ, dist)` setting is applied to all targets simultaneously (a “linked” scenario).
   The output file name is auto-generated based on `--targets`.

3. For each scenario (single-target or multi-prior) and each `(μ, σ, dist)` combination:
   - `main.py` runs `run_meridian_once.py` as a subprocess, writing a temporary CSV
   - `main.py` appends the temporary output into the master results file and deletes the temp file

4. Baseline tracking:
   - `main.py` passes `baseline_mu`, `baseline_sigma`, `baseline_dist` into every subprocess call
   - `run_meridian_once.py` marks `is_baseline=True` when the run’s `(roi_prior_mu, roi_prior_sigma, roi_prior_dist)` matches baseline

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

## How to Run

Run all commands from the **repo root**.

### Single-target mode (Base)

Run sensitivity for one or more target channels (the ROI prior is modified for each target channel **one at a time**):

- `python -m src.main --channels tiktok`
- `python -m src.main --channels meta google`
- `python -m src.main --channels all`

**Output:**
- `data/output/prior_sensitivity_results_tiktok.csv`
- `data/output/prior_sensitivity_results_meta_google.csv`
- `data/output/prior_sensitivity_results_all_channels.csv`

### Multi-prior mode (Expanded, linked)

Run sensitivity where multiple target channels are perturbed together using the same (μ, σ, dist) per iteration (“linked” scenario):

- `python -m src.main --targets meta tiktok`

**Output:**
- `data/output/prior_sensitivity_results_multi_meta_tiktok.csv`

## Tornado Ready Summary Table

After generating a sensitivity results CSV, export a tornado-ready summary table (baseline vs. new ROI + deltas) by running:

- `python -m src.summarize_sensitivity meta tiktok`
- `python -m src.summarize_sensitivity meta tiktok google`

### How input/output are chosen (no hard-coding)

`summarize_sensitivity.py` takes positional target channels (pairs, triples, etc.). It automatically:

1. Builds the expected multi-prior results filename:
   - **Input results CSV:** `data/output/prior_sensitivity_results_multi_<tag>.csv`

2. If the input results CSV does not exist, it automatically runs:
   - `python -m src.main --targets <targets...>`
   to generate the results file first.

3. Writes the tornado-ready output:
   - **Output tornado CSV:** `data/output/tornado_ready_<tag>.csv`

Where `<tag>` is the underscore-joined, sorted target list (e.g., `meta_tiktok`, `google_meta`, `google_meta_tiktok`).

### Output columns
- `targets, prior_key, channel, roi_baseline, roi_new, delta_abs, delta_pct`

### Notes
- Baseline is identified using `is_baseline == True` from the results CSV (set in `run_meridian_once.py` by comparing the run’s `roi_prior_mu/sigma/dist` to `baseline_mu/baseline_sigma/baseline_dist` passed from `main.py`).
- `delta_abs = |roi_new - roi_baseline|`
- `delta_pct = |roi_new/roi_baseline - 1|`

## Visualization

After generating sensitivity CSVs, you can create summary plots (basic ROI plots + heatmap + ranking):

- `python -m src.viz.prior_viz`

---


