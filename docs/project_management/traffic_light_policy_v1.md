# Traffic-Light Decision Policy v1 (Pre-Robustness-Score)

This policy defines how to assign decision tiers before the robustness score pipeline is fully integrated.

## Purpose
- Convert QC + diagnostics + sensitivity outputs into one decision tier for non-technical stakeholders.
- Keep model outputs usable for directional guidance while preventing overconfident budget actions.

## Rule Set
1. RED
- QC gate result is `FAIL`.
- Or QC gate is missing while diagnostics include at least one `FAIL` run.

2. YELLOW
- QC gate is `REVIEW` or missing.
- Or diagnostics exceed green limits.
- Or top sensitivity reaches the high threshold.

3. GREEN
- QC gate is `PASS`.
- Diagnostics remain within green limits.
- Top sensitivity is below the high threshold.

## Current Thresholds (from `config/report_google_meta_tiktok.yaml`)
- `high_sensitivity_pct`: 15.0
- `medium_sensitivity_pct`: 7.5
- Green limits:
  - `max_diag_fail_runs_for_green`: 0
  - `max_diag_review_runs_for_green`: 5

## Report Integration
- Decision Card displays:
  - Decision tier (`GREEN/YELLOW/RED`)
  - Triggered policy rules for current report run
  - Supporting reasons and next actions

## Next Upgrade (when robustness score is ready)
- Replace `Pending Robustness Score` with computed score (0-100).
- Add score-based overrides:
  - score < red threshold -> RED
  - score in warning band -> YELLOW
  - score >= green threshold + QC PASS -> GREEN
