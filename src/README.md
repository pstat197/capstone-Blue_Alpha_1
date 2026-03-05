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
- [Recommendation Stage](#recommendation-stage)
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
  - `baseline_sigma = cfg.roi_sigma_values[1]`
  - `baseline_dist = cfg.roi_dist_values[0]`

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

  - automatically locates split inputs:
    - `data/output/prior_sensitivity_runs_multi_<tag>.csv`
    - `data/output/prior_sensitivity_roi_multi_<tag>.csv`
  - if the split inputs do not exist, it will first run:
    - `python -m src.main --targets <targets...>`
    to generate the results
  - merges run and ROI rows by `run_id`
  - identifies baseline using `is_baseline == True`
  - computes:
    - `delta_abs = |roi_new - roi_baseline|`
    - `delta_pct = |roi_new/roi_baseline - 1|`
  - exports `data/output/tornado_<tag>.csv` with QC and impact columns

- `src/recommend_next_grid.py`
  Reads a tornado CSV and prints a next-iteration recommendation summary for a target set.

  - auto-runs `src.summarize_sensitivity` if the tornado file is missing
  - excludes `FAIL` runs from recommendation candidates
  - prints:
    - best stable next test (`PASS` only)
    - best aggressive next test (`PASS` + `REVIEW`)
    - flagged channels frequency to consider removing in the next linked run

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

### Multiplicative sensitivity (current default 3 points)
We vary both μ and σ by multiplicative factors:

`multipliers = {0.4, 1.0, 2.0}`

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
- `data/output/prior_sensitivity_runs_tiktok.csv`
- `data/output/prior_sensitivity_roi_tiktok.csv`
- `data/output/prior_sensitivity_runs_meta_google.csv`
- `data/output/prior_sensitivity_roi_meta_google.csv`
- `data/output/prior_sensitivity_runs_all.csv`
- `data/output/prior_sensitivity_roi_all.csv`

### Multi-prior mode (Expanded, linked)

Run sensitivity where multiple target channels are perturbed together using the same (μ, σ, dist) per iteration (“linked” scenario):

- `python -m src.main --targets meta tiktok`

**Output:**
- `data/output/prior_sensitivity_runs_multi_meta_tiktok.csv`
- `data/output/prior_sensitivity_roi_multi_meta_tiktok.csv`

## Tornado Ready Summary Table

After generating the split sensitivity outputs, export a tornado-ready summary table (baseline vs. new ROI plus deltas) by running:

- `python -m src.summarize_sensitivity meta tiktok`
- `python -m src.summarize_sensitivity meta tiktok google`

### How input/output are chosen (no hard-coding)

`summarize_sensitivity.py` takes positional target channels (pairs, triples, etc.). It automatically:

1. Looks for the current split files first:
   - **Run CSV:** `data/output/prior_sensitivity_runs_multi_<tag>.csv`
   - **ROI CSV:** `data/output/prior_sensitivity_roi_multi_<tag>.csv`

2. Merges the split files by `run_id`.

3. If the split files do not exist, it automatically runs:
   - `python -m src.main --targets <targets...>`
   to generate them first.

4. If only an older combined file exists, it still falls back to:
   - `data/output/prior_sensitivity_results_multi_<tag>.csv`

5. Writes the tornado-ready output:
   - **Output tornado CSV:** `data/output/tornado_<tag>.csv`

If you want dollar-valued impact columns, pass the subscription value explicitly, for example:

- default is `$100` per subscription, so the plain command already includes dollar-value columns
- short override: `python -m src.summarize_sensitivity google meta moloco --dps 125`
- long override: `python -m src.summarize_sensitivity google meta moloco --dollars_per_subscription 125`

Where `<tag>` is the underscore-joined, sorted target list (e.g., `meta_tiktok`, `google_meta`, `google_meta_tiktok`).

### Output columns
- core:
  - `run_id, targets, prior_key, channel, qc_status_code, qc_summary_short, qc_primary_review_check, qc_flagged_channels, roi_baseline, roi_new, delta_abs, delta_pct`
- impact columns (when spend data is available):
  - `channel_total_spend, incremental_outcome_baseline, incremental_outcome_new, delta_outcome, delta_outcome_abs`
- value columns (present by default with `--dps 100`):
  - `dollars_per_subscription, incremental_value_baseline, incremental_value_new, delta_value, delta_value_abs`

### Notes
- Baseline is identified after run/ROI merge using `is_baseline == True` from the run CSV.
- `delta_abs = |roi_new - roi_baseline|`
- `delta_pct = |roi_new/roi_baseline - 1|`

## Recommendation Stage

After the tornado CSV is generated, produce a standardized recommendation summary by target set:

- `python -m src.recommend_next_grid google meta moloco`
- `python -m src.recommend_next_grid google meta tiktok`
- `python -m src.recommend_next_grid beehiiv liveintent moloco`

What this stage does:

- reads `data/output/tornado_<tag>.csv`
- uses `delta_value_abs` when available (falls back to `delta_outcome_abs`, then `delta_abs`)
- excludes `FAIL` runs
- reports best stable and aggressive next-grid candidates
- reports flagged channels frequency in non-fail runs

This stage is intended to support expanded-stage iteration planning and handoff reporting.

## Diagnostic Guide

The run-level diagnostics come from `reviewer.ModelReviewer(mmm).run()` in `src/run_meridian_once.py`.

Each run stores:

- the full reviewer text in `qc_report_full`
- a compact rollup in `qc_status_code`, `qc_summary_short`, and `qc_primary_review_check`
- the individual check statuses in:
  - `qc_convergence_status`
  - `qc_baseline_status`
  - `qc_bayesianppp_status`
  - `qc_gof_status`
  - `qc_prior_posterior_shift_status`
  - `qc_roi_consistency_status`

### PASS

This means the overall reviewer status passed and no manual review was flagged.

Typical interpretation:

- convergence looked acceptable
- model fit looked acceptable
- the posterior learned enough from the data

### REVIEW:PriorPosteriorShift

This means the run did not fail, but at least one channel's posterior did not move enough away from its prior.

Typical interpretation:

- the prior may be too strong for that channel
- the channel signal may be weak
- the run is usable, but it needs review

Current example in `data/output/prior_sensitivity_runs_multi_google_meta_moloco.csv`:

- `qc_summary_short = REVIEW:PriorPosteriorShift`
- `qc_primary_review_check = PriorPosteriorShift`
- `qc_flagged_channels = moloco`

This matches the reviewer message that `moloco` did not significantly shift from the prior.

### FAIL:Baseline

This means the run is rolled up as a failure and the first non-pass check is `Baseline`.

Typical interpretation:

- the posterior probability that the baseline is negative is too high
- the model may have converged numerically, but the baseline decomposition is not reliable

Current example in `data/output/prior_sensitivity_runs_multi_google_meta_moloco.csv`:

- `qc_summary_short = FAIL:Baseline`
- `qc_primary_review_check = Baseline`
- `qc_baseline_neg_prob = 0.54`

### Convergence And Model-Fit Diagnostics

The run CSV keeps the reviewer-level convergence and fit statuses:

- `qc_convergence_status`
- `qc_bayesianppp_status`
- `qc_gof_status`

## Visualization

After generating sensitivity CSVs, you can create summary plots (basic ROI plots + heatmap + ranking):

- `python -m src.viz.prior_viz`

---


