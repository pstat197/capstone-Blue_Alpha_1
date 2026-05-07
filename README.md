# BlueAlpha Capstone 1: MMM ROI Prior Sensitivity

Bayesian prior-sensitivity workflow for Google Meridian MMM.

The current workflow runs an ROI-only prior sweep one target channel at a time. For each run, the pipeline varies the ROI prior for a single `target_channel`, fits Meridian, and keeps the primary output row where `channel == target_channel`. Other posterior model metrics may still be generated for reporting context, but contribution-prior mode has been removed.

For non-revenue KPIs, ROI analysis requires an explicit `outcome.revenue_per_kpi` assumption. In that case, ROI is interpreted and labeled as Revenue-equivalent ROI.

## What This Project Delivers

- ROI-only, one-channel-at-a-time prior sensitivity sweeps for Meridian MMM.
- Revenue-equivalent ROI support for non-revenue KPIs through `outcome.revenue_per_kpi`.
- Primary ROI outputs scoped to rows where `channel == target_channel`.
- Run-level QC/status outputs for reviewing model fit and sensitivity reliability.
- Robustness scoring and dashboard/report generation after the pipeline runs.
- Tornado/sensitivity tables and visualizations for prior robustness review.
- ROI prior vs posterior plot helper for the primary one-channel ROI CSV.
- Dashboard artifacts generated under `data/output/03_reports/report/<tag>/` after running the pipeline.

## Quickstart

From repo root:

```bash
python -m src.pipeline --config config/sensitivity.yaml
```

The active YAML config currently uses:

```yaml
run_mode: roi_full
parallel_workers: 4
prior_mode: roi
outcome:
  kpi_col: subscriptions
  kpi_type: non_revenue
  revenue_per_kpi: 40.0
```

Because `subscriptions` is configured as a non-revenue KPI, reported ROI is Revenue-equivalent ROI based on the explicit `revenue_per_kpi: 40.0` assumption.

## Target Selection

Active target selection is configured in `config/sensitivity.yaml`:

- `defaults.targets`: one linked target set.
- `defaults.target_sets`: optional batch run of multiple target sets.

`src.pipeline` uses YAML defaults when positional targets are omitted. CLI targets still work as an override:

```bash
python -m src.pipeline google --config config/sensitivity.yaml
python -m src.pipeline google tiktok --config config/sensitivity.yaml
```

Each target channel is swept one at a time. The primary ROI CSV should contain only the target-channel posterior row for each run.

## Outputs

Pipeline artifacts are generated under `data/output/` after a run. For a target tag `<tag>`:

- Runs CSV: `data/output/01_runs/<tag>/prior_sensitivity_runs_multi_<tag>.csv`
- Primary ROI CSV: `data/output/01_runs/<tag>/prior_sensitivity_roi_multi_<tag>.csv`
- Tornado CSV: `data/output/02_tables/<tag>/tornado_<tag>.csv`
- Report input CSV: `data/output/02_tables/<tag>/prior_sensitivity_report_input_<tag>.csv`
- Robustness CSVs: `data/output/02_tables/<tag>/robustness_*_<tag>.csv`
- Dashboard folder: `data/output/03_reports/report/<tag>/`
- Tornado plot folder: `data/output/03_reports/tornado_outputs/<tag>/`

Generated Google/Tiktok dashboard artifacts are not committed as current outputs. Run the pipeline to create fresh dashboard files for the configured target tag.

## Main Commands

```bash
# End-to-end YAML-first workflow
python -m src.pipeline --config config/sensitivity.yaml

# Sensitivity run only for selected target channels
python -m src.main --targets google --config config/sensitivity.yaml

# Build merged sensitivity/tornado table
python -m src.summarize_sensitivity google

# Compute robustness score
python -m src.robustness_score google

# Build dashboard after report input exists
python -m src.reporting.make_dashboard \
  --input data/output/02_tables/google/prior_sensitivity_report_input_google.csv \
  --outdir data/output/03_reports/report/google \
  --config config/dashboard.yaml \
  --clean-output

# Plot ROI prior vs posterior for primary one-channel rows
python -m src.viz.roi_prior_vs_posterior \
  --input data/output/01_runs/google/prior_sensitivity_roi_multi_google.csv \
  --output data/output/03_reports/tornado_outputs/google/roi_prior_vs_posterior_google.png
```

## Repo Map

```text
BLUEALPHA/
  config/          sensitivity + dashboard YAML configs
  data/
    raw/           input CSVs
    output/
      01_runs/     raw Meridian run outputs and primary ROI outputs per target tag
      02_tables/   merged sensitivity tables, tornado CSVs, robustness CSVs
      03_reports/  generated dashboards, figures, and tables
  docs/            theory, slides, interim reports, project management
  docs/notebooks/  Jupyter notebooks
  scripts/         utility scripts
  src/
    main.py                   ROI-only one-channel grid orchestrator
    run_meridian_once.py      single Meridian fit + QC + ROI extraction
    pipeline.py               one-command end-to-end runner
    summarize_sensitivity.py  post-run merge, baseline detection, tornado table
    robustness_score.py       robustness scoring
    run_config.py             YAML config loading, defaults, validation
    io_utils.py               CSV I/O, resume logic, column normalization
    output_paths.py           centralized output path management
    reporting/                dashboard + report generation
    viz/                      tornado and ROI prior/posterior plots
```

## Pipeline Flow

```text
config/sensitivity.yaml
        |
        v
src/main.py  -- one-channel ROI prior sweep -->  src/run_meridian_once.py
        |
        v
src/summarize_sensitivity.py
        |
        +--> src/viz/tornado_plots.py
        +--> src/robustness_score.py
        +--> src/reporting/make_dashboard.py --> dashboard artifacts
```

## Input Data (`data/raw/`)

| File | Rows | Description |
|------|-----:|-------------|
| `monthly_mocha.csv` | 73 | Primary national-level dataset (8 channels, KPI = subscriptions) |
| `monthly_mocha_geo.csv` | 74 | Same dataset with `state` + `population` columns for geo-level runs |
| `new_data.csv` | 24 | Alternate dataset (same channels, different time range) |
| `new_data_with_revenue.csv` | 24 | `new_data` with a revenue KPI column |

## Config Files (`config/`)

| File | Purpose |
|------|---------|
| `sensitivity.yaml` | Active ROI-only sensitivity config and single source of truth for the run grid/baseline |
| `dashboard.yaml` | Dashboard generation config (branding, thresholds, figure flags) |

## Notes

- Contribution-prior mode is no longer supported. If a config requests it, validation should fail.
- Posterior contribution metrics may still appear as Meridian outputs or dashboard context; they are not contribution-prior sensitivity mode.
- If the dataset has no valid geo column, the run is treated as national-level sensitivity. This is still useful for prior robustness, but not a true geo MMM experiment.

## Team

BlueAlpha Capstone Project 1 Group

- Jasper Luo
- Quinlan Wilson
- Jimmy Wu
- Aidan Frazier
- Coraline Zhu
