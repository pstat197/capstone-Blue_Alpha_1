from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.ticker import FuncFormatter


def _make_heatmap_pivot(merged: pd.DataFrame, channel: str, dist: str) -> pd.DataFrame:
    g = merged[
        (merged["channel"].astype(str) == str(channel))
        & (merged["roi_prior_dist"].astype(str) == str(dist))
    ].copy()
    pivot = g.pivot_table(
        index="roi_prior_mu",
        columns="roi_prior_sigma",
        values="pct_change",
        aggfunc="mean",
    ).sort_index().sort_index(axis=1)
    return pivot


def _compute_tornado_interval_summary(merged: pd.DataFrame, range_mode: str) -> pd.DataFrame:
    rows = []
    for channel, g in merged.groupby(["channel"], as_index=False):
        vals = g["pct_change"].dropna().to_numpy(dtype=float)
        if len(vals) == 0:
            continue

        if range_mode == "minmax":
            left = float(np.min(vals))
            right = float(np.max(vals))
        elif range_mode == "p05p95":
            left = float(np.quantile(vals, 0.05))
            right = float(np.quantile(vals, 0.95))
        else:
            raise ValueError("tornado_range_mode must be 'minmax' or 'p05p95'")

        rows.append(
            {
                "channel": channel,
                "left": left,
                "right": right,
                "impact": max(abs(left), abs(right)),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["channel", "left", "right", "impact"])

    return pd.DataFrame(rows).sort_values("impact", ascending=False).reset_index(drop=True)


def _slugify(value: str) -> str:
    out = []
    prev_dash = False
    for ch in str(value).strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        else:
            if not prev_dash:
                out.append("-")
                prev_dash = True
    slug = "".join(out).strip("-")
    return slug or "scenario"


def _format_dollar_axis(x: float, _pos: int) -> str:
    sign = "-" if x < 0 else ""
    ax = abs(float(x))
    if ax >= 1_000_000_000:
        return f"{sign}${ax/1_000_000_000:.1f}B"
    if ax >= 1_000_000:
        return f"{sign}${ax/1_000_000:.1f}M"
    if ax >= 1_000:
        return f"{sign}${ax/1_000:.0f}K"
    return f"{sign}${ax:,.0f}"


def _format_dollar_label(x: float) -> str:
    sign = "+" if x > 0 else "-" if x < 0 else ""
    ax = abs(float(x))
    if ax >= 1_000_000_000:
        return f"{sign}${ax/1_000_000_000:.2f}B"
    if ax >= 1_000_000:
        return f"{sign}${ax/1_000_000:.2f}M"
    if ax >= 1_000:
        return f"{sign}${ax/1_000:.1f}K"
    return f"{sign}${ax:,.0f}"


def _bluealpha_heatmap_cmap() -> LinearSegmentedColormap:
    # Diverging map centered at zero: project navy -> light -> warm accent.
    return LinearSegmentedColormap.from_list(
        "bluealpha_heatmap_div",
        [
            "#0f2d5c",
            "#3f73b7",
            "#f6fbff",
            "#f2c270",
            "#d88731",
            "#8f3f1d",
        ],
        N=256,
    )


def make_all_figures(df: pd.DataFrame, metrics: dict, cfg: dict, fig_dir: Path) -> dict:
    fig_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "tornado": None,
        "tornado_dollar": None,
        "scenario_snapshot": None,
        "scenario_snapshots": [],
        "heatmap_pages": [],
        "heatmap_modes": [],
        "default_heatmap_mode": None,
    }

    dpi = int(cfg["figures"].get("dpi", 160))

    if cfg["figures"].get("make_tornado", True):
        range_mode = str(cfg["figures"].get("tornado_range_mode", "p05p95")).strip().lower()
        top_n = int(cfg["figures"].get("tornado_top_n", cfg["ranking"]["top_n"]))
        summary = _compute_tornado_interval_summary(metrics["merged_df"], range_mode)
        summary = summary.head(top_n).sort_values("impact", ascending=True).reset_index(drop=True)

        labels = [str(r.channel).upper() for r in summary.itertuples(index=False)]
        y = np.arange(len(summary))
        left = summary["left"].to_numpy(dtype=float)
        right = summary["right"].to_numpy(dtype=float)
        widths = right - left

        fig, ax = plt.subplots(figsize=(11, 0.65 * len(summary) + 2.5))
        ax.axvline(0, color="black", linewidth=1.6)
        ax.barh(y, widths, left=left, alpha=0.9, color="#4f8fb9")

        max_abs = float(np.nanmax(np.abs(np.concatenate([left, right])))) if len(summary) > 0 else 1.0
        pad = 0.08 * max_abs if max_abs > 0 else 1.0
        ax.set_xlim(-(max_abs + pad), (max_abs + pad))
        ax.set_yticks(y)
        ax.set_yticklabels(labels)
        ax.set_xlabel("Change in estimated ROI (%), relative to baseline")
        linked = metrics.get("scope", {}).get("linked_targets", [])
        title = ", ".join(str(x).upper() for x in linked) if linked else "ROI TORNADO"
        ax.set_title(title)
        ax.grid(True, axis="x", alpha=0.25)

        for i, (l, r) in enumerate(zip(left, right)):
            ax.text(l, i, f"{l:+.1f}%", va="center", ha="right", fontsize=9)
            ax.text(r, i, f"{r:+.1f}%", va="center", ha="left", fontsize=9)
        fig.tight_layout()

        path = fig_dir / "tornado_top_sensitivity.png"
        fig.savefig(path, dpi=dpi, bbox_inches="tight")
        plt.close(fig)

        out["tornado"] = path.name

    dollar = metrics.get("dollar", {})
    if cfg["figures"].get("make_tornado", True) and dollar.get("available"):
        top_n = int(cfg["figures"].get("tornado_top_n", cfg["ranking"]["top_n"]))
        dsum = dollar["rank_df"].copy().head(top_n).sort_values("max_abs_dollar_change", ascending=True).reset_index(drop=True)
        labels = [str(r.channel).upper() for r in dsum.itertuples(index=False)]
        y = np.arange(len(dsum))
        left = dsum["left_dollar"].to_numpy(dtype=float)
        right = dsum["right_dollar"].to_numpy(dtype=float)
        widths = right - left

        max_abs = float(np.nanmax(np.abs(np.concatenate([left, right])))) if len(dsum) > 0 else 1.0
        pad = 0.08 * max_abs if max_abs > 0 else 1.0

        fig, ax = plt.subplots(figsize=(11, 0.65 * len(dsum) + 2.5))
        ax.axvline(0, color="black", linewidth=1.6)
        ax.barh(y, widths, left=left, alpha=0.9, color="#3d86b8")

        scope = metrics.get("scope", {})
        linked = scope.get("linked_targets", [])
        if linked:
            title = ", ".join(str(x).upper() for x in linked)
        else:
            title = "CHANNEL SENSITIVITY"

        dps_note = dollar.get("dollars_per_subscription_note", "unknown")
        if dps_note == "row-level varying":
            scale_note = "scaled by row-level 'dollars_per_subscription'"
        elif dps_note not in {"unknown", "", None}:
            scale_note = f"scaled by dollars_per_subscription={dps_note}"
        else:
            scale_note = "scaled by available value columns"

        ax.set_yticks(y)
        ax.set_yticklabels(labels)
        ax.set_xlabel(f"Change in incremental value ($), relative to baseline ({scale_note})")
        ax.set_title(title)
        ax.grid(True, axis="x", alpha=0.25)
        ax.set_xlim(-(max_abs + pad), (max_abs + pad))
        ax.xaxis.set_major_formatter(FuncFormatter(_format_dollar_axis))

        for i, (l, r) in enumerate(zip(left, right)):
            ax.text(l, i, _format_dollar_label(l), va="center", ha="right", fontsize=9)
            ax.text(r, i, _format_dollar_label(r), va="center", ha="left", fontsize=9)

        fig.tight_layout()

        dpath = fig_dir / "tornado_dollar_sensitivity.png"
        fig.savefig(dpath, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        out["tornado_dollar"] = dpath.name

    if cfg["figures"].get("make_scenario_snapshot", True):
        snap = metrics.get("scenario_snapshot", {})
        if snap.get("available"):
            scenarios = snap.get("scenarios", [])
            selected_run_id = str(snap.get("selected_run_id", ""))
            top_n = int(cfg["figures"].get("scenario_snapshot_top_n", 8))

            for i, item in enumerate(scenarios):
                snap_df = item["rows_df"].copy()
                if snap_df.empty:
                    continue
                snap_df = snap_df.sort_values("abs_pct_change", ascending=True).reset_index(drop=True)
                if top_n > 0:
                    snap_df = snap_df.tail(top_n)

                y = np.arange(len(snap_df))
                vals_raw = pd.to_numeric(snap_df["pct_change"], errors="coerce").to_numpy(dtype=float)
                vals = np.where(np.isfinite(vals_raw), vals_raw, 0.0)
                labels = snap_df["channel"].astype(str).tolist()
                colors = np.where(vals < 0, "#2f6ea9", "#e07a2d")

                meta = item.get("meta", {})
                mu = meta.get("roi_prior_mu", "NA")
                sigma = meta.get("roi_prior_sigma", "NA")
                dist = meta.get("roi_prior_dist", "NA")

                fig, ax = plt.subplots(figsize=(9.6, max(4.8, 0.52 * len(snap_df) + 2.2)))
                ax.axvline(0, color="#16313c", linewidth=1.3, alpha=0.9)
                ax.barh(y, vals, color=colors, alpha=0.92)

                max_abs = float(np.nanmax(np.abs(vals))) if len(vals) > 0 else 1.0
                if not np.isfinite(max_abs) or max_abs <= 0:
                    max_abs = 1.0
                pad = 0.1 * max_abs if max_abs > 0 else 1.0
                ax.set_xlim(-(max_abs + pad), (max_abs + pad))
                ax.set_yticks(y)
                ax.set_yticklabels(labels)
                ax.set_xlabel("ROI % change from baseline")
                ax.set_title(f"Single Scenario Snapshot (mu={mu}, sigma={sigma}, dist={dist})")
                ax.grid(True, axis="x", alpha=0.22)
                ax.legend(
                    handles=[
                        plt.Rectangle((0, 0), 1, 1, color="#2f6ea9", label="Negative Change"),
                        plt.Rectangle((0, 0), 1, 1, color="#e07a2d", label="Positive Change"),
                    ],
                    loc="lower right",
                    frameon=True,
                )
                fig.tight_layout()

                run_id = str(item.get("run_id", f"scenario_{i+1}"))
                fname = f"scenario_snapshot_{i+1:02d}_{_slugify(run_id)}.png"
                snap_path = fig_dir / fname
                fig.savefig(snap_path, dpi=dpi, bbox_inches="tight")
                plt.close(fig)

                out["scenario_snapshots"].append(
                    {
                        "run_id": run_id,
                        "path": fname,
                        "label": item.get("label", run_id),
                    }
                )
                if run_id == selected_run_id:
                    out["scenario_snapshot"] = fname

            if out["scenario_snapshot"] is None and out["scenario_snapshots"]:
                out["scenario_snapshot"] = out["scenario_snapshots"][0]["path"]

    if cfg["figures"].get("make_heatmaps", True):
        merged = metrics["merged_df"]
        rank = metrics["rank_df"].copy()

        rows = int(cfg["figures"].get("heatmap_grid_rows", 2))
        cols = int(cfg["figures"].get("heatmap_grid_cols", 2))
        page_size = max(1, rows * cols)
        top_n = int(cfg["figures"].get("heatmap_top_n", 8))

        selected = rank.head(top_n).copy()
        entries = list(selected.itertuples(index=False))
        cmap = _bluealpha_heatmap_cmap()
        annotate_cells = bool(cfg["figures"].get("heatmap_annotate_cells", True))

        default_scale_mode = str(cfg["figures"].get("heatmap_scale_mode", "robust_q95")).strip().lower()
        if default_scale_mode not in {"robust_q95", "abs_max"}:
            default_scale_mode = "robust_q95"
        compare_scales = bool(cfg["figures"].get("heatmap_compare_scales", True))

        scale_modes = [default_scale_mode]
        if compare_scales:
            for extra in ["robust_q95", "abs_max"]:
                if extra not in scale_modes:
                    scale_modes.append(extra)
        scale_label = {"robust_q95": "Robust Q95 Scale", "abs_max": "Full Abs-Max Scale"}
        out["default_heatmap_mode"] = default_scale_mode
        out["heatmap_modes"] = [
            {"mode": m, "label": scale_label.get(m, m)}
            for m in scale_modes
        ]

        for mode in scale_modes:
            for page_start in range(0, len(entries), page_size):
                chunk = entries[page_start: page_start + page_size]
                page_num = page_start // page_size + 1
                fig, axes = plt.subplots(rows, cols, figsize=(cols * 4.8, rows * 3.9), constrained_layout=True)
                axes_flat = np.atleast_1d(axes).ravel()

                pivots: list[tuple[object, pd.DataFrame]] = []
                abs_pool: list[float] = []
                for r in chunk:
                    pivot = _make_heatmap_pivot(merged, r.channel, r.roi_prior_dist)
                    pivots.append((r, pivot))
                    if not pivot.empty:
                        vals = pivot.values.astype(float)
                        finite = vals[np.isfinite(vals)]
                        if finite.size > 0:
                            abs_pool.extend(np.abs(finite).tolist())
                if abs_pool:
                    if mode == "abs_max":
                        page_abs_max = float(np.max(abs_pool))
                    else:
                        page_abs_max = float(np.quantile(np.asarray(abs_pool, dtype=float), 0.95))
                else:
                    page_abs_max = 0.0
                if not np.isfinite(page_abs_max) or page_abs_max <= 0:
                    page_abs_max = 1.0
                norm = TwoSlopeNorm(vmin=-page_abs_max, vcenter=0.0, vmax=page_abs_max)

                last_im = None
                for ax_i, ax in enumerate(axes_flat):
                    if ax_i >= len(chunk):
                        ax.axis("off")
                        continue

                    r, pivot = pivots[ax_i]
                    if pivot.empty:
                        ax.axis("off")
                        continue

                    values = pivot.values.astype(float)

                    im = ax.imshow(values, aspect="auto", cmap=cmap, norm=norm)
                    last_im = im

                    ax.set_title(
                        f"{r.channel} | {r.roi_prior_dist}\nmax |%|={float(r.max_abs_pct_change):.1f}%",
                        fontsize=9,
                    )
                    ax.set_xlabel("sigma", fontsize=8)
                    ax.set_ylabel("mu", fontsize=8)

                    ax.set_xticks(np.arange(len(pivot.columns)))
                    ax.set_xticklabels([f"{x:.2f}" for x in pivot.columns], rotation=40, ha="right", fontsize=7)
                    ax.set_yticks(np.arange(len(pivot.index)))
                    ax.set_yticklabels([f"{x:.2f}" for x in pivot.index], fontsize=7)

                    if annotate_cells:
                        for ri in range(values.shape[0]):
                            for ci in range(values.shape[1]):
                                v = values[ri, ci]
                                if not np.isfinite(v):
                                    continue
                                txt_color = "#f7fbff" if abs(v) >= (0.45 * page_abs_max) else "#122c4e"
                                ax.text(
                                    ci,
                                    ri,
                                    f"{v:.0f}",
                                    ha="center",
                                    va="center",
                                    fontsize=7,
                                    color=txt_color,
                                    fontweight=600,
                                )

                    # Mark baseline prior location for quick visual reference.
                    try:
                        mu0 = float(r.baseline_mu)
                        sigma0 = float(r.baseline_sigma)
                        y_idx = int(np.argmin(np.abs(np.asarray(pivot.index, dtype=float) - mu0)))
                        x_idx = int(np.argmin(np.abs(np.asarray(pivot.columns, dtype=float) - sigma0)))
                        ax.scatter(
                            [x_idx],
                            [y_idx],
                            marker="s",
                            s=52,
                            facecolors="none",
                            edgecolors="#081b36",
                            linewidths=1.2,
                        )
                    except Exception:
                        pass

                if last_im is not None:
                    fig.colorbar(
                        last_im,
                        ax=axes_flat.tolist(),
                        shrink=0.85,
                        label="ROI % change vs baseline",
                    )

                fig.suptitle(
                    f"Heatmap Board {page_num}: Prior-Sensitivity Surfaces (shared scale)",
                    fontsize=12,
                    y=1.01,
                )
                filename = f"heatmap_board_{page_num:02d}_{mode}.png"
                out_path = fig_dir / filename
                fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
                plt.close(fig)

                lo = page_start + 1
                hi = page_start + len(chunk)
                out["heatmap_pages"].append(
                    {
                        "path": f"figures/{filename}",
                        "caption": (
                            f"Top sensitivity entries {lo}-{hi} in 2x2 layout, shared color scale around 0, "
                            "with baseline grid cell outlined."
                        ),
                        "board_num": page_num,
                        "scale_mode": mode,
                        "scale_label": scale_label.get(mode, mode),
                        "is_default": mode == default_scale_mode,
                    }
                )

    return out
