# Dashboard Productization Notes

## Why this architecture

To move from a static capstone report to a client-facing product UI, we adopted a three-layer pattern used by production MMM systems:

1. Model/metrics layer (Python MMM outputs)
2. UI data contract layer (stable JSON payload)
3. Interactive frontend layer (stateful charts + filters)

## Source patterns we mapped

1. Google Meridian
- Meridian's scenario-planning stack separates modeling outputs from UI consumable structures and supports interactive planning workflows.
- Mapping: we now emit `tables/dashboard_payload.json` as the UI contract and render a separate interactive dashboard page.

2. Meta Robyn
- Robyn emphasizes decision-ready one-pagers, diagnostics, and budget/allocation context rather than raw model internals.
- Mapping: the dashboard surfaces decision tier, QC health, sensitivity leaderboard, and spend-vs-effect alignment in one screen.

3. Scrollytelling/data product practice (D3/Scrollama style)
- Progressive interaction and narrative presets help stakeholders quickly switch viewpoints.
- Mapping: added dashboard presets (`default`, `stress`, `normal`, `lognormal`) that instantly reconfigure filters and chart views.

4. Production charting frameworks (ECharts)
- High-performance, responsive interactive charts with robust tooltip/legend/resize behavior.
- Mapping: dashboard charts are ECharts-driven and react to global filters.

## What was implemented in this repo

1. New dashboard template
- File: `src/reporting/templates/dashboard_template.html`
- Includes:
  - Global control panel (distribution, metric, top-N, stable-only)
  - Story presets
  - Sensitivity Explorer chart
  - Spend vs Effect chart
  - QC donut chart
  - Scenario drill-down table
  - Filtered leaderboard + executive/recommendation lists

2. New payload contract generation
- File: `src/reporting/render.py`
- Added `dashboard_payload` build logic from existing metrics blocks.
- Writes JSON contract to `tables/dashboard_payload.json`.

3. Dashboard output generation in report pipeline
- File: `src/reporting/render.py`
- `make_report` now also renders `dashboard.html` (config-controlled).

4. Config toggles
- File: `config/report_google_meta_tiktok.yaml`
- Added:
  - `output.write_dashboard`
  - `output.dashboard_filename`
  - `output.dashboard_template`

## How to generate

```powershell
python -m src.reporting.make_report --input data/output/02_tables/google_meta_tiktok/prior_sensitivity_report_input_google_meta_tiktok.csv --outdir data/output/03_reports/report/google_meta_tiktok --clean-output
```

Expected outputs:

- `report.html`
- `dashboard.html`
- `tables/dashboard_payload.json`

## References

- Google Meridian docs and scenario planner:
  - https://developers.google.com/meridian/docs/basics/meridian-introduction
  - https://developers.google.com/meridian/docs/scenario-planning/meridian-scenario-planner
  - https://developers.google.com/meridian/reference/api/scenarioplanner
  - https://github.com/google/meridian
- Meta Robyn:
  - https://github.com/facebookexperimental/Robyn
  - https://facebookexperimental.github.io/Robyn/docs/features/
- Scrollytelling and charting foundations:
  - https://github.com/russellsamora/scrollama
  - https://github.com/d3/d3
  - https://echarts.apache.org/en/index.html
