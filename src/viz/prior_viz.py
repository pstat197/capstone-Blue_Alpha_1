from __future__ import annotations

import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from pathlib import Path
from typing import List, Optional, Tuple


# Repo paths (robust)
ROOT = Path(__file__).resolve().parents[2] 
DATA_OUT = ROOT / "data" / "output"
FIG_DIR = ROOT / "docs" / "figures"


DEFAULT_CHANNEL_ORDER = [
    "meta",
    "google",
    "snapchat",
    "tiktok",
    "moloco",
    "liveintent",
    "beehiiv",
    "amazon",
]


# 1) Merge per-channel CSVs
def merge_channel_results(
    channel_order: List[str] = DEFAULT_CHANNEL_ORDER,
    data_out_dir: Path = DATA_OUT,
    output_name: str = "prior_sensitivity_results_all_channels.csv",
    verbose: bool = True,
) -> Path:
    """
    Merge prior_sensitivity_results_{channel}.csv into one file with a 'channel' column.
    Looks for files under data_out_dir.
    Returns the path to the merged CSV.
    """
    all_dfs: List[pd.DataFrame] = []
    missing: List[str] = []

    for channel in channel_order:
        file_path = data_out_dir / f"prior_sensitivity_results_{channel}.csv"
        if not file_path.exists():
            missing.append(str(file_path))
            continue

        df = pd.read_csv(file_path)
        df["channel"] = channel
        all_dfs.append(df)

    if missing and verbose:
        print("Missing files:\n" + "\n".join(missing))

    if not all_dfs:
        raise FileNotFoundError(
            "No CSV files found for the specified channels under: "
            f"{data_out_dir}"
        )

    merged_df = pd.concat(all_dfs, ignore_index=True)

    output_path = data_out_dir / output_name
    merged_df.to_csv(output_path, index=False)

    if verbose:
        print(f"Saved merged file to: {output_path}")

    return output_path


# Helpers
def _load_df(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    req = {"target_channel", "channel", "estimated_roi"}
    missing = req - set(df.columns)
    if missing:
        raise ValueError(
            f"Missing required columns: {missing}\nFound: {df.columns.tolist()}"
        )

    df["estimated_roi"] = pd.to_numeric(df["estimated_roi"], errors="coerce")
    df = df.dropna(subset=["estimated_roi", "target_channel", "channel"])
    return df


# 2) Heatmap
def plot_prior_sensitivity_heatmap(
    csv_path: Path,
    out_dir: Path = FIG_DIR / "heatmap",
    fname_base: str = "prior_sensitivity_heatmap",
    cmap: str = "viridis",
    figsize: Tuple[int, int] = (12, 8),
    dpi: int = 300,
    show: bool = False,
) -> Tuple[Path, Path]:
    """
    Creates a heatmap of ROI range (max-min) for each (target_channel, channel).
    Saves PNG and PDF, returns their paths.
    """
    df = _load_df(csv_path)

    ranges = (
        df.groupby(["target_channel", "channel"], as_index=False)["estimated_roi"]
          .agg(roi_range=lambda x: x.max() - x.min())
    )

    pivot = ranges.pivot(index="target_channel", columns="channel", values="roi_range")
    mask = pivot.isna()

    pivot = pivot.where(np.eye(pivot.shape[0], pivot.shape[1], dtype=bool))

    plt.figure(figsize=figsize)
    ax = sns.heatmap(
        pivot,
        annot=True,
        fmt=".3f",
        cmap=cmap,
        linewidths=0.8,
        linecolor="white",
        mask=mask,
        cbar_kws={"label": "ROI Range (max − min)"},
        annot_kws={"size": 11},
    )

    ax.set_title("Prior Sensitivity Heatmap (ROI Range across Prior Mean Sweep)", pad=12)
    ax.set_xlabel("Affected Channel (posterior ROI tracked)")
    ax.set_ylabel("Target Channel (prior varied)")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha="right")
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0)

    plt.tight_layout()

    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / f"{fname_base}.png"
    pdf_path = out_dir / f"{fname_base}.pdf"

    plt.savefig(png_path, dpi=dpi, bbox_inches="tight")
    plt.savefig(pdf_path, bbox_inches="tight")

    if show:
        plt.show()
    plt.close()

    print("Saved:", png_path)
    print("Saved:", pdf_path)

    return png_path, pdf_path


# 3) Sensitivity Ranking (bar plot)
def plot_prior_sensitivity_ranking(
    csv_path: Path,
    diag_only: bool = True,
    out_dir: Path = FIG_DIR / "sensitivity_ranking",
    fname_base: str = "prior_sensitivity_ranking",
    figsize: Tuple[int, int] = (10, 6),
    dpi: int = 300,
    show: bool = False,
) -> Tuple[Path, Path]:
    """
    Ranks channels by ROI range (max-min) across sweep.
    If diag_only=True, only uses rows where target_channel == channel.
    Saves PNG and PDF, returns their paths.
    """
    df = _load_df(csv_path)

    if diag_only:
        df_use = df[df["target_channel"].astype(str) == df["channel"].astype(str)].copy()
    else:
        df_use = df.copy()

    sensitivity = (
        df_use.groupby("target_channel")["estimated_roi"]
              .agg(lambda x: np.nanmax(x) - np.nanmin(x))
              .reset_index(name="roi_range")
              .sort_values("roi_range", ascending=False)
    )

    sns.set_theme(style="whitegrid")

    plt.figure(figsize=figsize)
    ax = sns.barplot(data=sensitivity, x="roi_range", y="target_channel", orient="h")

    ax.set_title("Prior Sensitivity Ranking (ROI Range across Sweep)")
    ax.set_xlabel("ROI Range (max − min)")
    ax.set_ylabel("Target Channel (prior varied)")

    # annotate bars
    max_range = sensitivity["roi_range"].max() if len(sensitivity) else 0.0
    for p in ax.patches:
        width = p.get_width()
        ax.text(
            width + 0.01 * max_range,
            p.get_y() + p.get_height() / 2,
            f"{width:.3f}",
            va="center",
        )

    plt.tight_layout()

    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / f"{fname_base}.png"
    pdf_path = out_dir / f"{fname_base}.pdf"

    plt.savefig(png_path, dpi=dpi, bbox_inches="tight")
    plt.savefig(pdf_path, bbox_inches="tight")

    if show:
        plt.show()
    plt.close()

    print("Saved:", png_path)
    print("Saved:", pdf_path)

    return png_path, pdf_path


# CLI entry
def main():
    merged_csv = merge_channel_results()

    plot_prior_sensitivity_heatmap(merged_csv, show=False)
    plot_prior_sensitivity_ranking(merged_csv, diag_only=True, show=False)


if __name__ == "__main__":
    main()