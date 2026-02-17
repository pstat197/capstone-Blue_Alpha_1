# Meridian Prior Sensitivity Code

This folder contains the runnable scripts for fitting Meridian MMM models and running a prior sensitivity analysis on the ROI prior mean (μ) using the Mocha dataset.

---

## Table of Contents

- [Meridian Prior Sensitivity Code](#src--meridian-prior-sensitivity-code)
  - [Overview](#overview)
  - [Repo Layout (within `src`)](#repo-layout-within-src)
  - [How the Pipeline Works](#how-the-pipeline-works)
  - [Choosing ROI Prior Mean (μ)](#choosing-roi-prior-mean-μ)
    - [Step 1 — Data-Calibrated Baseline](#step-1--data-calibrated-baseline)
    - [Step 2 — Wide Sensitivity via Multipliers](#step-2--wide-sensitivity-via-multipliers)
    - [Step 3 — Coarse-to-Fine Refinement](#step-3--coarse-to-fine-refinement)
    - [Step 4 — Quick Sanity Check](#step-4--quick-sanity-check)
---

## Overview

- **Goal:** Evaluate how sensitive Meridian ROI estimates are to the assumed ROI prior mean (μ).
- **Dataset:** `monthly_mocha.csv` (subscriptions KPI + channel media variables).
- **Approach:** Run Meridian with multiple μ settings (a coarse grid first), compare ROI results, and refine around values where results change materially.

---

## Repo Layout (within `src`)

- `main.py`  
  Runs the full prior sensitivity experiment (loops over channels × μ grid, calls `run_meridian_once.py`, aggregates outputs).

- `experiment.py`  
  Centralizes experiment configuration and **data-calibrated μ grid construction**:
  - loads the Mocha CSV
  - detects spend columns (`{channel}_spend`)
  - computes baseline μ0 = median(subscriptions / total_spend)
  - generates μ grid via `μ = μ0 × multipliers`
  - returns a structured `ExperimentConfig` (paths, channels, μ values)

- `run_meridian_once.py`  
  Fits one Meridian model for a given target channel + μ and extracts ROI outputs.
- `utils.py`  
  Shared helper functions (build model spec/priors, extract ROI summaries).

---

## How the Pipeline Works

1. `experiment.py` loads `data/raw/monthly_mocha.csv` and constructs the experiment configuration:
   - identifies spend columns as `{channel}_spend`
   - computes a data-calibrated baseline center:
     `μ0 = median(subscriptions / total_spend)`
   - builds the sensitivity grid:
     `μ_grid = μ0 × {0.4, 0.7, 1.0, 1.4, 2.0}`

2. `main.py` reads `ExperimentConfig` from `experiment.py` and loops over each `(target_channel, μ)` pair.

3. For each run, `main.py` calls `run_meridian_once.py` as a subprocess, passing:
   - dataset path
   - full channel list (JSON)
   - target channel
   - μ value
   - sampling params and output CSV path

4. `run_meridian_once.py` builds the Meridian model spec (using `utils.py`), fits the model, and writes a run-level ROI summary.

5. `main.py` aggregates all run-level outputs into a single results file:
   - `data/output/prior_sensitivity_results_5mu.csv`

---

## Choosing ROI Prior Mean (μ) for Sensitivity Analysis

Because the Mocha dataset is a single monthly/weekly dataset and we do not have historical ROI experiments, lift tests, or benchmark priors, we set the ROI prior mean (μ) using a data-calibrated scale and then conduct wide prior sensitivity using multiplicative changes (percent shifts), rather than an arbitrary additive step.

In this project, ROI is naturally interpreted on the scale:

`ROI ≈ incremental_subscriptions / spend`  (subscriptions per dollar)


From the dataset, a typical scale can be approximated using medians:

- median(subscriptions) ≈ 11,580  
- median(total spend) ≈ 211,250  

So a naive baseline scale is:

`ROI_0 ≈ 11580 / 211250`  (subscriptions per dollar)

---

### Step 1 — Data-calibrated baseline center (weakly-informative)
Without external priors, we set a weakly-informative baseline center:

`μ0 = median(subscriptions / total_spend) = 0.055`


This does not claim causality; it anchors μ to the correct order of magnitude so the sensitivity experiment is meaningful.

---

### Step 2 — Wide sensitivity using multiplicative shifts
To address uncertainty (no experiments/benchmarks), we vary μ by multiplicative factors around μ0, which corresponds to interpretable percent changes (e.g., 1.2×, 1.4×). Because ROI is a ratio-scale quantity, multiplicative perturbations are more meaningful than an additive step.

#### Coarse wide grid (5 points, log-symmetric)
We first run a coarse grid designed to be roughly balanced in log-space (up/down factors are approximately reciprocal):

`μ ∈ μ0 × {0.4, 0.7, 1.0, 1.4, 2.0}`

With \(\mu_0 \approx 0.055\), this is approximately:

- 0.022, 0.0385, 0.055, 0.077, 0.110

#### Optional wider grid (7 points)
If broader stress-testing is needed:

`μ ∈ μ0 × {0.2, 0.4, 0.7, 1.0, 1.4, 2.0, 3.0}`


---

### Step 3 — Coarse-to-fine refinement
We use a coarse grid first to reduce computation. If results change materially between adjacent settings (e.g., between 1.0× and 1.4×), we refine by adding intermediate values such as:

`μ ∈ μ0 × {1.2, 1.3}`

If results are stable across `{0.7, 1.0, 1.4}, we do not add more points.

---

### Step 4 — Quick “reasonableness” sanity check
We ensure μ values do not imply implausibly large incremental outcomes. A rough implied incremental scale is:

`implied incremental subscriptions ≈ μ × (typical spend)`


Using median spend ≈ 211,000:

- at `μ = 0.165`: implied incremental subs ≈ 0.165 × 211k ≈ 34,800  
  (≈ 3× the median observed subscriptions ≈ 11.6k)

If a candidate μ implies outcomes on the order of 10×–50× the observed KPI, the range is considered too wide and is adjusted.


