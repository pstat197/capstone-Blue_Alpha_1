from __future__ import annotations
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np


def make_all_figures(df: pd.DataFrame, metrics: dict, cfg: dict, fig_dir: Path) -> dict:
    fig_dir.mkdir(parents=True, exist_ok=True)
    out = {"tornado": None, "per_target": {}}

    dpi = int(cfg["figures"].get("dpi", 160))

    if cfg["figures"].get("make_tornado", True):
        rank_top = metrics["rank_top_df"].copy()

        rank_top = rank_top.sort_values("max_abs_pct_change", ascending=True).reset_index(drop=True)

        labels = [
            f"{r.target_channel} ({r.roi_prior_dist})"
            for r in rank_top.itertuples(index=False)
        ]
        values = rank_top["max_abs_pct_change"].to_numpy()

        plt.figure(figsize=(8, 5.5))
        y = np.arange(len(rank_top))
        plt.barh(y, values)
        plt.yticks(y, labels)
        plt.xlabel("Max |% Change| from Baseline (%)")
        plt.title("Tornado: Most Sensitive Targets")
        plt.tight_layout()

        path = fig_dir / "tornado_top_sensitivity.png"
        plt.savefig(path, dpi=dpi, bbox_inches="tight")
        plt.close()

        out["tornado"] = path.name

    if cfg["figures"].get("make_heatmaps", True):
        merged = metrics["merged_df"]

        for (tgt, dist), g in merged.groupby(["target_channel", "roi_prior_dist"]):
            pivot = g.pivot_table(
                index="roi_prior_mu",
                columns="roi_prior_sigma",
                values="pct_change",
                aggfunc="mean"
            ).sort_index().sort_index(axis=1)

            plt.figure(figsize=(6.5, 4.8))
            im = plt.imshow(pivot.values, aspect="auto")
            plt.title(f"Heatmap: % Change vs Baseline\nTarget={tgt}, Dist={dist}")
            plt.xlabel("roi_prior_sigma")
            plt.ylabel("roi_prior_mu")
            plt.xticks(
                ticks=np.arange(len(pivot.columns)),
                labels=[f"{x:.2f}" for x in pivot.columns],
                rotation=45
            )
            plt.yticks(
                ticks=np.arange(len(pivot.index)),
                labels=[f"{x:.2f}" for x in pivot.index]
            )
            plt.colorbar(im, label="% change")
            plt.tight_layout()

            filename = f"heatmap_{tgt}_{dist}.png".replace(" ", "_")
            path = fig_dir / filename
            plt.savefig(path, dpi=dpi, bbox_inches="tight")
            plt.close()

            out["per_target"][(tgt, dist)] = f"figures/{filename}"

    return out