"""Plot one-channel ROI prior-vs-posterior results."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create the ROI: Prior vs Posterior plot from the primary one-channel ROI CSV."
    )
    parser.add_argument("--input", required=True, help="Primary one-channel ROI CSV.")
    parser.add_argument("--output", required=True, help="Output PNG path.")
    parser.add_argument(
        "--title",
        default="ROI: Prior vs Posterior",
        help="Plot title.",
    )
    return parser


def _require_columns(df: pd.DataFrame, columns: list[str]) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Input CSV missing required columns: {missing}")


def _uses_revenue_equivalent_roi(df: pd.DataFrame) -> bool:
    if "revenue_per_kpi" not in df.columns:
        return False
    revenue_per_kpi = pd.to_numeric(df["revenue_per_kpi"], errors="coerce")
    return bool((revenue_per_kpi > 0).any())


def make_plot(input_csv: str | Path, output_png: str | Path, *, title: str = "ROI: Prior vs Posterior") -> Path:
    input_path = Path(input_csv)
    output_path = Path(output_png)
    df = pd.read_csv(input_path)
    _require_columns(
        df,
        [
            "target_channel",
            "channel",
            "roi_prior_mu",
            "roi_prior_sigma",
            "roi_prior_dist",
            "estimated_roi",
            "posterior_roi_p25",
            "posterior_roi_p75",
            "prior_roi_mu_channel",
        ],
    )

    target_mask = df["channel"].astype(str) == df["target_channel"].astype(str)
    ignored_rows = int((~target_mask).sum())
    df = df[target_mask].copy()
    if df.empty:
        raise ValueError("No primary one-channel rows found where channel == target_channel.")
    if not (df["channel"].astype(str) == df["target_channel"].astype(str)).all():
        raise ValueError("Primary ROI rows must satisfy channel == target_channel.")

    if ignored_rows:
        print(f"Ignored {ignored_rows} non-target ROI rows where channel != target_channel.")

    lo_col, hi_col = "posterior_roi_p25", "posterior_roi_p75"
    numeric_cols = ["roi_prior_mu", "roi_prior_sigma", "estimated_roi", "prior_roi_mu_channel", lo_col, hi_col]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["target_channel", "estimated_roi", "prior_roi_mu_channel", lo_col, hi_col])
    if df.empty:
        raise ValueError("No plottable rows remained after numeric parsing.")

    channels = sorted(df["target_channel"].astype(str).unique().tolist())
    y_base = {channel: idx for idx, channel in enumerate(channels)}
    variants = (
        df[["roi_prior_mu", "roi_prior_sigma"]]
        .drop_duplicates()
        .sort_values(["roi_prior_mu", "roi_prior_sigma"])
        .itertuples(index=False)
    )
    variant_keys = [(float(row.roi_prior_mu), float(row.roi_prior_sigma)) for row in variants]
    variant_count = max(len(variant_keys), 1)
    offsets = {
        key: ((idx - (variant_count - 1) / 2.0) * min(0.035, 0.65 / max(variant_count, 1)))
        for idx, key in enumerate(variant_keys)
    }

    cmap = plt.get_cmap("tab20")
    colors = {key: cmap(idx % cmap.N) for idx, key in enumerate(variant_keys)}

    height = max(5.0, 0.7 * len(channels) + 1.5)
    fig, ax = plt.subplots(figsize=(12, height))
    legend_handles = {}

    for row in df.itertuples(index=False):
        key = (float(row.roi_prior_mu), float(row.roi_prior_sigma))
        y = y_base[str(row.target_channel)] + offsets.get(key, 0.0)
        x = float(row.estimated_roi)
        lo = float(getattr(row, lo_col))
        hi = float(getattr(row, hi_col))
        color = colors.get(key, "C0")
        label = f"mu={key[0]:g}, sigma={key[1]:g}"
        handle = ax.errorbar(
            x,
            y,
            xerr=[[max(0.0, x - lo)], [max(0.0, hi - x)]],
            fmt="o",
            color=color,
            ecolor=color,
            elinewidth=1.3,
            capsize=2,
            markersize=4,
            alpha=0.9,
            label=label if label not in legend_handles else None,
        )
        legend_handles.setdefault(label, handle)
        ax.scatter(
            float(row.prior_roi_mu_channel),
            y,
            marker="D",
            s=28,
            color="#8a8f98",
            edgecolor="white",
            linewidth=0.4,
            zorder=3,
        )

    ax.axvline(1.0, color="#666666", linestyle="--", linewidth=1.0, alpha=0.8)
    ax.set_yticks([y_base[ch] for ch in channels])
    ax.set_yticklabels(channels)
    x_label = "Revenue-equivalent ROI" if _uses_revenue_equivalent_roi(df) else "ROI"
    ax.set_xlabel(x_label)
    ax.set_ylabel("Channel")
    ax.set_title(title)
    ax.grid(axis="x", color="#e4e7eb", linewidth=0.8)
    ax.set_axisbelow(True)

    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(
            handles,
            labels,
            title="Prior variants",
            loc="center left",
            bbox_to_anchor=(1.01, 0.5),
            fontsize=8,
            title_fontsize=9,
        )

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def main() -> None:
    args = _build_parser().parse_args()
    out = make_plot(args.input, args.output, title=args.title)
    print(f"Saved ROI prior-vs-posterior plot to: {out}")


if __name__ == "__main__":
    main()
