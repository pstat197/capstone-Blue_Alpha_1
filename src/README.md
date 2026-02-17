# Meridian Prior Sensitivity Code

This folder contains the runnable scripts for fitting Meridian MMM models and running a prior sensitivity analysis on the ROI prior mean (μ) using the Mocha dataset.

---

## Table of Contents

- [Meridian Prior Sensitivity Code](#src--meridian-prior-sensitivity-code)
  - [Overview](#overview)
  - [Repo Layout (within `src`)](#repo-layout-within-src)
  - [How the Pipeline Works](#how-the-pipeline-works)
  - [Inputs and Outputs](#inputs-and-outputs)
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
  Runs the full prior sensitivity experiment (loops over channels × μ grid, aggregates results).
- `run_meridian_once.py`  
  Fits one Meridian model for a given target channel + μ and extracts ROI outputs.
- `utils.py`  
  Shared helper functions (build model spec/priors, extract ROI summaries).

---

## How the Pipeline Works

1. `main.py` defines the sensitivity grid of μ values and target channels.
2. For each `(channel, μ)` combination, `main.py` calls `run_meridian_once.py`.
3. `run_meridian_once.py` builds the Meridian model spec (often via `utils.py`), fits the model, and extracts ROI summaries.
4. `main.py` aggregates run-level ROI results into a single results table.

---

## Inputs and Outputs

### Inputs
- Dataset CSV (e.g., `data/raw/monthly_mocha.csv`)
- Target channel(s) for sensitivity runs
- μ grid (ROI prior mean values)

### Outputs
- A combined results CSV summarizing ROI estimates across all runs  
  (e.g., `data/output/prior_sensitivity_results.csv`)

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
We use a coarse grid firs* to reduce computation. If results change materially between adjacent settings (e.g., between 1.0× and 1.4×), we refine by adding intermediate values such as:

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


