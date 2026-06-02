# Modeling Source

Runnable Python code for BlueAlpha prior-sensitivity analysis with Google Meridian.

This folder owns the modeling pipeline: read config, run ROI-prior sweeps, summarize sensitivity, compute robustness, and build the React dashboard payload.

## Run The Pipeline

From the repository root:

```bash
python -m src.pipeline --config config/sensitivity.yaml
```

To run selected target channels:

```bash
python -m src.pipeline google --config config/sensitivity.yaml
python -m src.pipeline google tiktok --config config/sensitivity.yaml
```

The pipeline resolves targets from CLI arguments first. If no CLI targets are provided, it uses `defaults.target_sets` or `defaults.targets` from the YAML config.

## Pipeline Steps

`src.pipeline` orchestrates these steps:

1. `src.main`: run the ROI prior sweep and write raw run/ROI outputs.
2. `src.summarize_sensitivity`: merge outputs and build tornado/sensitivity tables.
3. `src.robustness_score`: compute channel and model robustness summaries.
4. `src.reporting.make_dashboard`: write React-readable dashboard payload and supporting tables.

Each step can be skipped with pipeline flags such as `--skip-main`, `--skip-summarize`, `--skip-robustness`, and `--skip-dashboard` when reusing existing outputs.

## Config Contract

Primary config lives in `config/sensitivity.yaml`.

Important fields:

- `model.data_csv`: input dataset path
- `model.time_col`: date/time column
- `outcome.kpi_col`: KPI column
- `outcome.kpi_type`: revenue or non-revenue KPI mode
- `outcome.revenue_per_kpi`: required when the KPI is non-revenue and ROI must be revenue-equivalent
- `defaults.targets` or `defaults.target_sets`: target channels to perturb
- `sweep.type`: default workflow is `fixed_full_grid`
- `priors`: ROI prior grid values
- `sampler`: Meridian sampling settings
- `output.tag`: optional explicit output tag

Minimum dataset columns:

- time column, usually `date`
- KPI column from the config
- for each channel `c`: `{c}_impressions` and `{c}_spend`

## Output Contract

For output tag `<tag>`, the standard outputs are:

```text
data/output/01_runs/<tag>/prior_sensitivity_runs_multi_<tag>.csv
data/output/01_runs/<tag>/prior_sensitivity_roi_multi_<tag>.csv
data/output/02_tables/<tag>/prior_sensitivity_report_input_<tag>.csv
data/output/02_tables/<tag>/tornado_<tag>.csv
data/output/02_tables/<tag>/robustness_channel_<tag>.csv
data/output/02_tables/<tag>/robustness_model_<tag>.csv
data/output/02_tables/<tag>/robustness_run_channel_metrics_<tag>.csv
data/output/03_reports/report/<tag>/tables/dashboard_payload.json
```

The current dashboard runtime reads `dashboard_payload.json`; old static `dashboard.html` generation is no longer the main path.

## Core Modules

- `pipeline.py`: end-to-end orchestrator
- `main.py`: ROI-only grid runner
- `run_meridian_once.py`: one Meridian fit, diagnostics, and ROI extraction
- `run_config.py`: YAML loading, defaults, and validation
- `io_utils.py`: CSV I/O, column normalization, resume helpers
- `output_paths.py`: centralized output path helpers
- `baseline_utils.py`: explicit baseline-row validation
- `summarize_sensitivity.py`: sensitivity and tornado table construction
- `robustness_score.py`: project-defined robustness scoring
- `build_report_input.py`: report input assembly helper
- `reporting/metrics.py`: dashboard metric preparation
- `reporting/render.py`: `dashboard_payload.json` writer
- `reporting/make_dashboard.py`: dashboard payload CLI entrypoint
- `viz/`: optional research/export plots

## Robustness Score

`robustness_score.py` writes the canonical channel score as `overall_channel_robustness_score`.

The score is project-defined, not an official Meridian metric:

```text
overall_channel_robustness_score =
  0.60 * prior_sensitivity_subscore
  + 0.25 * data_influence_subscore
  + 0.15 * cross_channel_subscore
```

Bands are fixed project thresholds:

- Low: `< 50`
- Medium: `50-74`
- High: `>= 75`

Relative rank fields compare channels only within the current output. Rank `1` means most robust in that result set, not universally robust.

## Prior Parameterization

For `LogNormal` ROI priors, config values `roi_mu` and `roi_sigma` are treated as natural-scale mean and standard deviation targets. The code converts those values to log-space parameters before constructing the TensorFlow Probability distribution.

## Optional Utilities

Optional plotting/export helpers live in `src/viz/`:

- `tornado_plots.py`
- `roi_prior_vs_posterior.py`

These are manual research/export utilities. The React app reads generated payload tables instead of depending on standalone PNG plots.

## Troubleshooting

- `Configured data CSV does not exist`: check `model.data_csv` in the YAML config.
- Missing KPI or channel columns: verify the dataset has the configured KPI plus `{channel}_impressions` and `{channel}_spend`.
- Missing `revenue_per_kpi`: add it when using a non-revenue KPI.
- Permission errors while writing outputs: close open CSV/HTML files in Excel, browser, or preview tools.
- Very large percent changes: inspect `Delta ROI`, stability flags, and near-zero baseline fields before interpreting percent movement.
