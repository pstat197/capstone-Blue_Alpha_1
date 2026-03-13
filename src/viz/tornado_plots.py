import argparse
import json
from datetime import datetime
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

REPO_ROOT = Path(__file__).resolve().parents[2]

CSV_NAME = "data/output/02_tables/google_meta_tiktok/tornado_google_meta_tiktok.csv"
CSV_GLOB = "data/output/02_tables/*/tornado_*.csv"
INPUT_MODE = "all"  # "single" or "all"
OUT_DIR = "data/output/03_reports/tornado_outputs"

RANGE_MODE = "p05p95"   # "minmax" or "p05p95"
TOP_N = 20

CHANNEL_COL = "channel"
PRIOR_KEY_COL = "prior_key"
SPEND_COL = "channel_total_spend"
ROI_BASELINE_COL = "roi_baseline"
ROI_NEW_COL = "roi_new"

# Preferred generalizable inputs
OUTCOME_BASELINE_COL = "incremental_outcome_baseline"
OUTCOME_NEW_COL = "incremental_outcome_new"
PRICE_COL = "dollars_per_subscription"

# Fallback if direct dollar-value columns already exist
VALUE_BASELINE_COL = "incremental_value_baseline"
VALUE_NEW_COL = "incremental_value_new"

# Subscription scaling control for generalization:
# - "dataset": use row-level dollars_per_subscription from the input CSV
# - "fixed": force a constant subscription amount for all rows
SUBSCRIPTION_SCALING_MODE = "dataset"  # "dataset" or "fixed"
FIXED_SUBSCRIPTION_AMOUNT = 100.0

# Disable CSV dataset outputs by default; keep only the tornado figure output.
WRITE_SUMMARY_DATASETS = False

# HTML outputs for report integration.
WRITE_HTML_REPORT = True
WRITE_HTML_FRAGMENT = True
WRITE_GLOBAL_REPORT = False

# Objective for selecting the "best" overall prior distribution setup.
# - "total_new_value": maximize total dollar incremental value under changed priors
# - "total_delta_value": maximize dollar improvement vs baseline
# - "overall_roi_new": maximize aggregate ROI
BEST_CONFIG_OBJECTIVE = "total_new_value"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate tornado sensitivity plots/reports from tornado CSV outputs.",
    )
    parser.add_argument(
        "--input-mode",
        choices=["single", "all"],
        default=INPUT_MODE,
        help="Use one CSV (--csv) or all matching CSVs (--glob).",
    )
    parser.add_argument(
        "--csv",
        default=CSV_NAME,
        help="CSV path relative to repo root when --input-mode=single.",
    )
    parser.add_argument(
        "--glob",
        dest="csv_glob",
        default=CSV_GLOB,
        help="Glob pattern relative to repo root when --input-mode=all.",
    )
    parser.add_argument(
        "--outdir",
        default=OUT_DIR,
        help="Output directory for plots/reports, relative to repo root.",
    )
    parser.add_argument(
        "--range-mode",
        choices=["minmax", "p05p95"],
        default=RANGE_MODE,
        help="Range used to build tornado bars.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=TOP_N,
        help="Maximum number of channels in each tornado chart.",
    )
    parser.add_argument(
        "--subscription-scaling-mode",
        choices=["dataset", "fixed"],
        default=SUBSCRIPTION_SCALING_MODE,
        help="Value scaling mode for outcome-to-dollar conversion.",
    )
    parser.add_argument(
        "--fixed-subscription-amount",
        type=float,
        default=FIXED_SUBSCRIPTION_AMOUNT,
        help="Fixed dollar amount when --subscription-scaling-mode=fixed.",
    )
    parser.add_argument(
        "--best-config-objective",
        choices=["total_new_value", "total_delta_value", "overall_roi_new"],
        default=BEST_CONFIG_OBJECTIVE,
        help="Objective used to choose the best prior setup in report tables.",
    )
    parser.add_argument(
        "--write-summary-datasets",
        action="store_true",
        help="Write per-scenario summary CSV files in addition to plots/reports.",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Disable HTML report outputs and generate PNG plots only.",
    )
    parser.add_argument(
        "--no-html-fragment",
        action="store_true",
        help="Disable HTML fragment output files.",
    )
    parser.add_argument(
        "--write-global-report",
        action="store_true",
        help="Write cross-scenario global sensitivity report (mainly for --input-mode all).",
    )
    return parser


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _fmt_money(x: float) -> str:
    if pd.isna(x):
        return "NA"
    sign = "-" if x < 0 else ""
    ax = abs(float(x))
    if ax >= 1_000_000_000:
        return f"{sign}${ax/1_000_000_000:.2f}B"
    if ax >= 1_000_000:
        return f"{sign}${ax/1_000_000:.2f}M"
    if ax >= 1_000:
        return f"{sign}${ax/1_000:.1f}K"
    return f"{sign}${ax:,.0f}"


def _fmt_delta_money(x: float) -> str:
    if pd.isna(x):
        return "NA"
    if x > 0:
        return f"+{_fmt_money(x)}".replace("+-", "-")
    return _fmt_money(x)


def _fmt_pct(x: float) -> str:
    if pd.isna(x):
        return "NA"
    return f"{x:.2%}"


def _fmt_delta_ratio(x: float) -> str:
    if pd.isna(x):
        return "NA"
    sign = "+" if x > 0 else ""
    return f"{sign}{x:.4f}"


def _prior_key_summary(prior_key_str: str) -> str:
    try:
        d = json.loads(prior_key_str)
    except Exception:
        return str(prior_key_str)
    if not isinstance(d, dict):
        return str(prior_key_str)

    parts = []
    for ch in sorted(d.keys()):
        cfg = d[ch] if isinstance(d[ch], dict) else {}
        dist = cfg.get("dist", "NA")
        mu = cfg.get("mu", "NA")
        sigma = cfg.get("sigma", "NA")
        parts.append(f"{str(ch).upper()}: {dist}(mu={mu}, sigma={sigma})")
    return " | ".join(parts)


def _slugify(value: str) -> str:
    raw = str(value).strip().lower()
    out = []
    prev_dash = False
    for ch in raw:
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        else:
            if not prev_dash:
                out.append("-")
                prev_dash = True
    slug = "".join(out).strip("-")
    return slug or "report-section"


def _parse_targets(raw: str) -> list[str]:
    if raw is None:
        return []
    txt = str(raw).strip()
    if not txt:
        return []

    parsed = None
    try:
        parsed = json.loads(txt)
    except Exception:
        parsed = None

    if isinstance(parsed, list):
        items = [str(x) for x in parsed]
    elif isinstance(parsed, dict):
        items = [str(k) for k in parsed.keys()]
    else:
        items = [p.strip() for p in txt.split(",")]

    seen = set()
    out = []
    for item in items:
        ch = str(item).strip().upper()
        if not ch or ch in seen:
            continue
        seen.add(ch)
        out.append(ch)
    return out


def infer_changed_channels(df: pd.DataFrame) -> list[str]:
    if "targets" in df.columns:
        for raw in df["targets"].dropna().tolist():
            channels = _parse_targets(raw)
            if channels:
                return channels

    if CHANNEL_COL in df.columns:
        channels = (
            df[CHANNEL_COL].dropna().astype(str).str.upper().drop_duplicates().tolist()
        )
        return channels
    return []


def _legacy_single_csv_candidates(rel_path: str) -> list[str]:
    normalized = rel_path.replace("\\", "/")
    name = Path(normalized).name
    candidates = [normalized]
    if normalized != f"data/output/02_tables/{name}":
        candidates.append(f"data/output/02_tables/{name}")
    candidates.append(f"data/output/{name}")

    out = []
    seen = set()
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def collect_input_csv_paths(repo_root: Path) -> list[Path]:
    if INPUT_MODE == "single":
        tried = []
        for rel in _legacy_single_csv_candidates(CSV_NAME):
            p = repo_root / rel
            tried.append(str(p))
            if p.exists():
                return [p]

        raise FileNotFoundError(f"CSV not found. Tried: {', '.join(tried)}")

    if INPUT_MODE == "all":
        patterns = [CSV_GLOB, "data/output/02_tables/tornado_*.csv", "data/output/tornado_*.csv"]

        found: list[Path] = []
        seen: set[Path] = set()
        for pattern in patterns:
            for p in sorted(repo_root.glob(pattern)):
                if p.is_file():
                    rp = p.resolve()
                    if rp not in seen:
                        seen.add(rp)
                        found.append(p)
        paths = found
        if not paths:
            raise FileNotFoundError(
                f"No CSV files found in {repo_root} matching '{CSV_GLOB}'"
            )
        return paths

    raise ValueError("INPUT_MODE must be 'single' or 'all'")


def _build_tornado_explanation(summ: pd.DataFrame) -> str:
    if summ.empty:
        return "No valid channel rows were available to compute tornado sensitivity."

    s = summ.sort_values("impact", ascending=False).reset_index(drop=True)
    top = s.head(min(3, len(s)))
    top_bits = []
    for _, r in top.iterrows():
        top_bits.append(
            f"{str(r['channel']).upper()} ({_fmt_money(r['left'])} to {_fmt_money(r['right'])})"
        )

    upside = s.sort_values("right", ascending=False).iloc[0]
    downside = s.sort_values("left", ascending=True).iloc[0]

    txt = (
        f"Largest sensitivity ranges are in {'; '.join(top_bits)}. "
        f"Biggest upside scenario is {str(upside['channel']).upper()} at {_fmt_money(upside['right'])}, "
        f"while the largest downside scenario is {str(downside['channel']).upper()} at {_fmt_money(downside['left'])}. "
        "Bars crossing zero indicate the channel can either help or hurt depending on prior assumptions; "
        "wider bars indicate greater uncertainty and model sensitivity."
    )
    return txt


def compute_best_configuration(df: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    if PRIOR_KEY_COL not in df.columns:
        raise KeyError(
            f"Missing '{PRIOR_KEY_COL}' required to identify best prior distribution."
        )

    work = df.copy()
    if SPEND_COL in work.columns:
        work[SPEND_COL] = _to_numeric(work[SPEND_COL])
    else:
        work[SPEND_COL] = np.nan

    g = (
        work.groupby(PRIOR_KEY_COL, as_index=False)
        .agg(
            total_baseline_value=("value_baseline_used", "sum"),
            total_new_value=("value_new_used", "sum"),
            total_delta_value=("delta_value_used", "sum"),
            total_spend=(SPEND_COL, "sum"),
            n_rows=(CHANNEL_COL, "count"),
        )
        .copy()
    )

    g["overall_roi_baseline"] = g["total_baseline_value"] / g["total_spend"]
    g["overall_roi_new"] = g["total_new_value"] / g["total_spend"]
    g["overall_delta_roi"] = g["overall_roi_new"] - g["overall_roi_baseline"]
    g["prior_summary"] = g[PRIOR_KEY_COL].apply(_prior_key_summary)

    objective_map = {
        "total_new_value": "total_new_value",
        "total_delta_value": "total_delta_value",
        "overall_roi_new": "overall_roi_new",
    }
    if BEST_CONFIG_OBJECTIVE not in objective_map:
        raise ValueError(
            "BEST_CONFIG_OBJECTIVE must be one of: "
            "'total_new_value', 'total_delta_value', 'overall_roi_new'"
        )
    objective_col = objective_map[BEST_CONFIG_OBJECTIVE]
    best_idx = g[objective_col].idxmax()
    best = g.loc[best_idx].copy()
    best["objective_col"] = objective_col

    return best, g.sort_values(objective_col, ascending=False).reset_index(drop=True)


def build_html_report(
    outpath: Path,
    fragment_path: Path | None,
    csv_name: str,
    plot_path: Path,
    section_id: str,
    changed_channels: list[str],
    subscription_scale_note: str,
    best: pd.Series,
    top_configs: pd.DataFrame,
    channel_details: pd.DataFrame,
    summ: pd.DataFrame,
):
    tornado_text = _build_tornado_explanation(summ)
    objective_col = str(best.get("objective_col", "total_new_value"))

    channels_html = channel_details.to_html(
        index=False,
        border=0,
        justify="left",
        classes="tbl",
        escape=False,
    )
    top_configs_html = top_configs.to_html(
        index=False,
        border=0,
        justify="left",
        classes="tbl",
        escape=False,
    )
    changed_channels_txt = ", ".join(changed_channels) if changed_channels else "UNKNOWN"

    section_html = f"""
<section id="{escape(section_id)}">
  <h2>Tornado Dollar Sensitivity Summary</h2>
  <p><strong>Input CSV:</strong> {escape(csv_name)}</p>
  <p><strong>Channels altered:</strong> {escape(changed_channels_txt)}</p>
  <p><strong>Value Scaling:</strong> {escape(subscription_scale_note)}</p>
  <h3>Best Overall Prior Distribution Setup</h3>
  <p><strong>Selection objective:</strong> {escape(objective_col)}</p>
  <p><strong>Best prior setup:</strong> {escape(str(best['prior_summary']))}</p>
  <ul>
    <li><strong>Total baseline incremental value:</strong> {_fmt_money(best['total_baseline_value'])}</li>
    <li><strong>Total new incremental value:</strong> {_fmt_money(best['total_new_value'])}</li>
    <li><strong>Overall dollar change vs baseline:</strong> {_fmt_delta_money(best['total_delta_value'])}</li>
    <li><strong>Overall ROI change when channels were changed:</strong> {_fmt_delta_ratio(best['overall_delta_roi'])} ({_fmt_pct(best['overall_delta_roi'])})</li>
  </ul>
  <h3>Top Prior Setups (By Objective)</h3>
  {top_configs_html}
  <h3>Channel Effects At Best Setup</h3>
  {channels_html}
  <h3>Tornado Plot Interpretation</h3>
  <p>{escape(tornado_text)}</p>
  <img src="{escape(plot_path.name)}" alt="Tornado plot: channel sensitivity in dollar value" style="max-width:100%;height:auto;border:1px solid #ccc;" />
</section>
""".strip()

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Tornado Dollar Sensitivity Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; line-height: 1.45; margin: 24px; color: #111; }}
    h2, h3 {{ margin-bottom: 8px; }}
    p {{ margin: 6px 0 10px; }}
    ul {{ margin-top: 0; }}
    .tbl {{ border-collapse: collapse; width: 100%; margin: 8px 0 14px; }}
    .tbl th, .tbl td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; }}
    .tbl th {{ background: #f7f7f7; }}
    .meta {{ color: #555; font-size: 0.92rem; }}
  </style>
</head>
<body>
  <div class="meta">Generated {escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}</div>
  {section_html}
</body>
</html>
"""

    outpath.write_text(html_doc, encoding="utf-8")
    if fragment_path is not None:
        fragment_path.write_text(section_html, encoding="utf-8")


def compute_incremental_value(df: pd.DataFrame) -> pd.DataFrame:
    """
    Preferred:
        incremental_value = incremental_outcome * dollars_per_subscription

    Fallback:
        use incremental_value columns directly
    """
    df = df.copy()

    has_outcome = all(
        col in df.columns for col in [OUTCOME_BASELINE_COL, OUTCOME_NEW_COL]
    )
    has_value = all(
        col in df.columns for col in [VALUE_BASELINE_COL, VALUE_NEW_COL]
    )

    if SUBSCRIPTION_SCALING_MODE not in {"dataset", "fixed"}:
        raise ValueError("SUBSCRIPTION_SCALING_MODE must be 'dataset' or 'fixed'")

    if SUBSCRIPTION_SCALING_MODE == "fixed":
        sub_amount = float(FIXED_SUBSCRIPTION_AMOUNT)
        sub_scale = pd.Series(sub_amount, index=df.index, dtype=float)
        scale_label = f"fixed_${sub_amount:,.2f}"
    else:
        if PRICE_COL in df.columns:
            sub_scale = _to_numeric(df[PRICE_COL])
            if sub_scale.isna().all():
                raise ValueError(f"'{PRICE_COL}' has no numeric values to scale by.")
            scale_label = "dataset_row_level"
        else:
            sub_scale = None
            scale_label = "dataset_value_columns"

    if has_outcome:
        if sub_scale is None:
            raise KeyError(
                f"'{PRICE_COL}' is required with outcome columns when "
                "SUBSCRIPTION_SCALING_MODE='dataset'"
            )
        baseline_outcome = _to_numeric(df[OUTCOME_BASELINE_COL])
        new_outcome = _to_numeric(df[OUTCOME_NEW_COL])

        df["value_baseline_used"] = baseline_outcome * sub_scale
        df["value_new_used"] = new_outcome * sub_scale
        df["value_source"] = f"outcome_scaled_by_subscription_{scale_label}"
    elif has_value:
        baseline_value = _to_numeric(df[VALUE_BASELINE_COL])
        new_value = _to_numeric(df[VALUE_NEW_COL])

        if SUBSCRIPTION_SCALING_MODE == "fixed":
            if PRICE_COL not in df.columns:
                raise KeyError(
                    f"'{PRICE_COL}' is required to rescale value columns in fixed mode."
                )
            raw_price = _to_numeric(df[PRICE_COL]).replace(0, np.nan)
            rescale = float(FIXED_SUBSCRIPTION_AMOUNT) / raw_price
            df["value_baseline_used"] = baseline_value * rescale
            df["value_new_used"] = new_value * rescale
            df["value_source"] = (
                "incremental_value_columns_rescaled_to_fixed_subscription"
            )
        else:
            df["value_baseline_used"] = baseline_value
            df["value_new_used"] = new_value
            df["value_source"] = "incremental_value_columns_dataset_scale"
    else:
        raise KeyError(
            "Need either outcome columns or direct value columns.\n"
            f"Expected either:\n"
            f"  - {OUTCOME_BASELINE_COL}, {OUTCOME_NEW_COL}\n"
            f"or:\n"
            f"  - {VALUE_BASELINE_COL}, {VALUE_NEW_COL}"
        )

    return df


def format_dollar_axis(x, pos):
    sign = "-" if x < 0 else ""
    ax = abs(x)
    if ax >= 1_000_000_000:
        return f"{sign}${ax/1_000_000_000:.1f}B"
    if ax >= 1_000_000:
        return f"{sign}${ax/1_000_000:.1f}M"
    if ax >= 1_000:
        return f"{sign}${ax/1_000:.0f}K"
    return f"{sign}${ax:,.0f}"


def format_dollar_label(x):
    sign = "+" if x > 0 else "-" if x < 0 else ""
    ax = abs(x)
    if ax >= 1_000_000_000:
        return f"{sign}${ax/1_000_000_000:.2f}B"
    if ax >= 1_000_000:
        return f"{sign}${ax/1_000_000:.2f}M"
    if ax >= 1_000:
        return f"{sign}${ax/1_000:.1f}K"
    return f"{sign}${ax:,.0f}"


def plot_interval_by_channel(
    summ: pd.DataFrame, title: str, outpath: Path, subscription_scale_note: str
):
    if summ.empty:
        print("No data to plot.")
        return

    # least sensitive at bottom, most sensitive at top
    s = summ.sort_values("impact", ascending=True).reset_index(drop=True)

    y = np.arange(len(s))
    left = s["left"].to_numpy()
    right = s["right"].to_numpy()
    widths = right - left

    max_abs = float(np.max(np.abs(np.concatenate([left, right]))))
    pad = 0.08 * max_abs if max_abs > 0 else 1.0

    fig, ax = plt.subplots(figsize=(11, 0.65 * len(s) + 2.5))
    ax.axvline(0, color="black", linewidth=1.6)

    ax.barh(y, widths, left=left, alpha=0.9)

    ax.set_yticks(y)
    ax.set_yticklabels([str(c).upper() for c in s["channel"]])
    ax.set_xlabel(
        f"Change in incremental value ($), relative to baseline ({subscription_scale_note})"
    )
    ax.set_title(title)
    ax.grid(True, axis="x", alpha=0.25)
    ax.set_xlim(-(max_abs + pad), (max_abs + pad))
    ax.xaxis.set_major_formatter(FuncFormatter(format_dollar_axis))

    for i, (l, r) in enumerate(zip(left, right)):
        ax.text(l, i, format_dollar_label(l), va="center", ha="right", fontsize=9)
        ax.text(r, i, format_dollar_label(r), va="center", ha="left", fontsize=9)

    fig.tight_layout()
    fig.savefig(outpath, dpi=220, bbox_inches="tight")
    plt.close(fig)


def compute_channel_sensitivity_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ch, g in df.groupby(CHANNEL_COL):
        deltas = g["delta_value_used"].dropna().to_numpy()
        if len(deltas) == 0:
            continue

        if RANGE_MODE == "minmax":
            left = float(np.min(deltas))
            right = float(np.max(deltas))
        elif RANGE_MODE == "p05p95":
            left = float(np.quantile(deltas, 0.05))
            right = float(np.quantile(deltas, 0.95))
        else:
            raise ValueError("RANGE_MODE must be 'minmax' or 'p05p95'")

        impact = max(abs(left), abs(right))
        rows.append(
            {
                "channel": ch,
                "left": left,
                "right": right,
                "impact": impact,
                "range_width": right - left,
                "mean": float(np.mean(deltas)),
                "std": float(np.std(deltas, ddof=1)) if len(deltas) > 1 else 0.0,
                "n": int(len(deltas)),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "channel",
                "left",
                "right",
                "impact",
                "range_width",
                "mean",
                "std",
                "n",
            ]
        )

    return pd.DataFrame(rows).sort_values("impact", ascending=False).reset_index(drop=True)


def aggregate_global_channel_sensitivity(all_summ: pd.DataFrame) -> pd.DataFrame:
    if all_summ.empty:
        return pd.DataFrame()

    agg = (
        all_summ.groupby("channel", as_index=False)
        .agg(
            scenarios_present=("scenario_stem", "nunique"),
            observations=("impact", "size"),
            mean_impact=("impact", "mean"),
            median_impact=("impact", "median"),
            max_impact=("impact", "max"),
            worst_case_left=("left", "min"),
            best_case_right=("right", "max"),
            mean_range_width=("range_width", "mean"),
        )
        .sort_values(["mean_impact", "max_impact"], ascending=False)
        .reset_index(drop=True)
    )
    return agg


def build_global_sensitivity_report(
    outpath: Path,
    fragment_path: Path | None,
    agg: pd.DataFrame,
    scenarios_count: int,
):
    if agg.empty:
        raise ValueError("No scenario summaries available for global report.")

    top = agg.iloc[0]
    display = agg.copy()
    display["channel"] = display["channel"].astype(str).str.upper()
    for col in [
        "mean_impact",
        "median_impact",
        "max_impact",
        "worst_case_left",
        "best_case_right",
        "mean_range_width",
    ]:
        display[col] = display[col].map(_fmt_money)

    ranking_html = display.to_html(
        index=False,
        border=0,
        justify="left",
        classes="tbl",
        escape=False,
    )

    section_html = f"""
<section id="tornado-global-sensitivity">
  <h2>Global Channel Sensitivity Across All Scenarios</h2>
  <p><strong>Scenarios processed:</strong> {int(scenarios_count)}</p>
  <p><strong>Ranking rule:</strong> channels sorted by mean impact (max(|p05|, |p95|) per scenario).</p>
  <p><strong>Most sensitive overall channel:</strong> {escape(str(top['channel']).upper())}
     (mean impact {_fmt_money(top['mean_impact'])}, worst case {_fmt_money(top['worst_case_left'])},
      best case {_fmt_money(top['best_case_right'])}).</p>
  {ranking_html}
</section>
""".strip()

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Global Tornado Sensitivity Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; line-height: 1.45; margin: 24px; color: #111; }}
    h2, h3 {{ margin-bottom: 8px; }}
    p {{ margin: 6px 0 10px; }}
    .tbl {{ border-collapse: collapse; width: 100%; margin: 8px 0 14px; }}
    .tbl th, .tbl td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; }}
    .tbl th {{ background: #f7f7f7; }}
    .meta {{ color: #555; font-size: 0.92rem; }}
  </style>
</head>
<body>
  <div class="meta">Generated {escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}</div>
  {section_html}
</body>
</html>
"""
    outpath.write_text(html_doc, encoding="utf-8")
    if fragment_path is not None:
        fragment_path.write_text(section_html, encoding="utf-8")


def process_single_csv(csv_path: Path, out_dir: Path) -> dict:
    csv_stem = csv_path.stem
    df = pd.read_csv(csv_path)
    if df.empty:
        raise ValueError(f"CSV has no rows: {csv_path.name}")

    needed = {CHANNEL_COL}
    missing = needed - set(df.columns)
    if missing:
        raise KeyError(f"Missing required columns in {csv_path.name}: {sorted(missing)}")

    df = compute_incremental_value(df)
    df["delta_value_used"] = df["value_new_used"] - df["value_baseline_used"]
    subscription_scale_note = (
        f"scaled by fixed subscription ${FIXED_SUBSCRIPTION_AMOUNT:,.2f}"
        if SUBSCRIPTION_SCALING_MODE == "fixed"
        else f"scaled by row-level '{PRICE_COL}'"
    )

    changed_channels = infer_changed_channels(df)
    plot_title = ", ".join(changed_channels) if changed_channels else csv_stem.upper()

    summ = compute_channel_sensitivity_summary(df)
    if INPUT_MODE == "single":
        plot_path = out_dir / f"channel_sensitivity_tornado_dollar_value_{RANGE_MODE}.png"
    else:
        plot_path = out_dir / f"{csv_stem}_channel_sensitivity_tornado_dollar_value_{RANGE_MODE}.png"
    plot_interval_by_channel(
        summ.head(TOP_N),
        title=plot_title,
        outpath=plot_path,
        subscription_scale_note=subscription_scale_note,
    )

    if WRITE_SUMMARY_DATASETS:
        if INPUT_MODE == "single":
            summ_csv = out_dir / f"channel_sensitivity_summary_dollar_value_{RANGE_MODE}.csv"
        else:
            summ_csv = out_dir / f"{csv_stem}_channel_sensitivity_summary_dollar_value_{RANGE_MODE}.csv"
        summ.to_csv(summ_csv, index=False)
    else:
        summ_csv = None

    best, best_ranked = compute_best_configuration(df)
    best_prior_key = best[PRIOR_KEY_COL]
    best_rows = df[df[PRIOR_KEY_COL] == best_prior_key].copy()
    best_rows["roi_delta_channel"] = (
        _to_numeric(best_rows[ROI_NEW_COL]) - _to_numeric(best_rows[ROI_BASELINE_COL])
        if ROI_NEW_COL in best_rows.columns and ROI_BASELINE_COL in best_rows.columns
        else np.nan
    )
    best_rows = best_rows.sort_values("delta_value_used", ascending=False)
    channel_details = (
        best_rows[[CHANNEL_COL, "delta_value_used", "roi_delta_channel"]]
        .rename(
            columns={
                CHANNEL_COL: "channel",
                "delta_value_used": "delta_value",
                "roi_delta_channel": "delta_roi",
            }
        )
        .copy()
    )
    channel_details["delta_value"] = channel_details["delta_value"].map(_fmt_delta_money)
    channel_details["delta_roi"] = channel_details["delta_roi"].map(_fmt_pct)
    channel_details["channel"] = channel_details["channel"].astype(str).str.upper()

    top_configs = best_ranked.head(5)[
        [
            "prior_summary",
            "total_new_value",
            "total_delta_value",
            "overall_delta_roi",
        ]
    ].copy()
    top_configs = top_configs.rename(
        columns={
            "prior_summary": "prior_setup",
            "total_new_value": "total_new_value",
            "total_delta_value": "delta_value_vs_baseline",
            "overall_delta_roi": "delta_roi",
        }
    )
    top_configs["total_new_value"] = top_configs["total_new_value"].map(_fmt_money)
    top_configs["delta_value_vs_baseline"] = top_configs["delta_value_vs_baseline"].map(
        _fmt_delta_money
    )
    top_configs["delta_roi"] = top_configs["delta_roi"].map(_fmt_pct)

    if INPUT_MODE == "single":
        html_report_path = out_dir / "tornado_dollar_report.html"
        html_fragment_path = out_dir / "tornado_dollar_report_fragment.html" if WRITE_HTML_FRAGMENT else None
    else:
        html_report_path = out_dir / f"{csv_stem}_tornado_dollar_report.html"
        html_fragment_path = (
            out_dir / f"{csv_stem}_tornado_dollar_report_fragment.html"
            if WRITE_HTML_FRAGMENT
            else None
        )
    if WRITE_HTML_REPORT:
        build_html_report(
            outpath=html_report_path,
            fragment_path=html_fragment_path,
            csv_name=csv_path.name,
            plot_path=plot_path,
            section_id=f"tornado-dollar-{_slugify(csv_stem)}",
            changed_channels=changed_channels,
            subscription_scale_note=subscription_scale_note,
            best=best,
            top_configs=top_configs,
            channel_details=channel_details,
            summ=summ,
        )

    scenario_summary = summ.copy()
    scenario_summary["scenario_csv"] = csv_path.name
    scenario_summary["scenario_stem"] = csv_stem
    scenario_summary["changed_channels"] = ", ".join(changed_channels)
    scenario_summary["k_changed"] = len(changed_channels)

    return {
        "csv_name": csv_path.name,
        "plot_path": plot_path,
        "summ_csv": summ_csv,
        "html_report_path": html_report_path if WRITE_HTML_REPORT else None,
        "html_fragment_path": html_fragment_path,
        "scenario_summary": scenario_summary,
    }


def main():
    global CSV_NAME
    global CSV_GLOB
    global INPUT_MODE
    global OUT_DIR
    global RANGE_MODE
    global TOP_N
    global SUBSCRIPTION_SCALING_MODE
    global FIXED_SUBSCRIPTION_AMOUNT
    global WRITE_SUMMARY_DATASETS
    global WRITE_HTML_REPORT
    global WRITE_HTML_FRAGMENT
    global WRITE_GLOBAL_REPORT
    global BEST_CONFIG_OBJECTIVE

    args = _build_parser().parse_args()
    CSV_NAME = args.csv
    CSV_GLOB = args.csv_glob
    INPUT_MODE = args.input_mode
    OUT_DIR = args.outdir
    RANGE_MODE = args.range_mode
    TOP_N = int(args.top_n)
    SUBSCRIPTION_SCALING_MODE = args.subscription_scaling_mode
    FIXED_SUBSCRIPTION_AMOUNT = float(args.fixed_subscription_amount)
    WRITE_SUMMARY_DATASETS = bool(args.write_summary_datasets)
    WRITE_HTML_REPORT = not bool(args.no_html)
    WRITE_HTML_FRAGMENT = (not bool(args.no_html)) and (not bool(args.no_html_fragment))
    WRITE_GLOBAL_REPORT = bool(args.write_global_report)
    BEST_CONFIG_OBJECTIVE = args.best_config_objective

    if TOP_N < 1:
        raise ValueError("--top-n must be >= 1")

    out_dir = REPO_ROOT / OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_paths = collect_input_csv_paths(REPO_ROOT)

    scenario_summaries = []
    failures = []

    for csv_path in csv_paths:
        try:
            result = process_single_csv(csv_path=csv_path, out_dir=out_dir)
            scenario_summaries.append(result["scenario_summary"])
            print(f"\n[{result['csv_name']}] Saved:")
            print(" -", result["plot_path"])
            if result["summ_csv"] is not None:
                print(" -", result["summ_csv"])
            if result["html_report_path"] is not None:
                print(" -", result["html_report_path"])
            if result["html_fragment_path"] is not None:
                print(" -", result["html_fragment_path"])
        except Exception as exc:
            failures.append((csv_path.name, str(exc)))
            print(f"\n[{csv_path.name}] ERROR: {exc}")

    if not scenario_summaries:
        raise RuntimeError("No scenario reports were produced.")

    all_summ = pd.concat(scenario_summaries, ignore_index=True)
    global_agg = aggregate_global_channel_sensitivity(all_summ)

    if WRITE_HTML_REPORT and WRITE_GLOBAL_REPORT and INPUT_MODE == "all":
        global_html_report_path = out_dir / "tornado_global_sensitivity_report.html"
        global_html_fragment_path = (
            out_dir / "tornado_global_sensitivity_report_fragment.html"
            if WRITE_HTML_FRAGMENT
            else None
        )
        build_global_sensitivity_report(
            outpath=global_html_report_path,
            fragment_path=global_html_fragment_path,
            agg=global_agg,
            scenarios_count=len(csv_paths) - len(failures),
        )
        print("\n[GLOBAL] Saved:")
        print(" -", global_html_report_path)
        if global_html_fragment_path is not None:
            print(" -", global_html_fragment_path)

    if WRITE_GLOBAL_REPORT and not global_agg.empty:
        top_channel = str(global_agg.iloc[0]["channel"]).upper()
        print(f"\nMost sensitive overall channel (mean impact): {top_channel}")

    if failures:
        print("\nFailures:")
        for name, err in failures:
            print(f" - {name}: {err}")


if __name__ == "__main__":
    main()
