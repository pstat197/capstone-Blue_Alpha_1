import argparse
import os
import sys
import subprocess
from collections import Counter

import pandas as pd


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("targets", nargs="+")
    parser.add_argument(
        "--include-all-channels",
        action="store_true",
        help="Rank using all channels in the tornado file instead of only the target channels.",
    )
    return parser


def _tag_for_targets(targets: list[str]) -> str:
    return "_".join(sorted(str(t) for t in targets))


def _tornado_path(project_root: str, tag: str) -> str:
    return os.path.join(project_root, "data", "output", f"tornado_{tag}.csv")


def _ensure_tornado_exists(project_root: str, targets: list[str], path: str) -> None:
    if os.path.exists(path):
        return

    cmd = [sys.executable, "-m", "src.summarize_sensitivity"] + sorted(str(t) for t in targets)
    print("Tornado CSV missing; generating it first via:")
    print(" ".join(cmd))
    proc = subprocess.run(cmd, cwd=project_root)
    if proc.returncode != 0:
        raise RuntimeError(f"Auto-run of src.summarize_sensitivity failed with exit code {proc.returncode}")

    if not os.path.exists(path):
        raise FileNotFoundError(f"Expected tornado CSV still not found: {path}")


def _pick_score_columns(df: pd.DataFrame) -> tuple[str, str | None]:
    if "delta_value_abs" in df.columns:
        return "delta_value_abs", "delta_value"
    if "delta_outcome_abs" in df.columns:
        return "delta_outcome_abs", "delta_outcome"
    return "delta_abs", None


def _parse_run_id(run_id: str) -> dict:
    parts = str(run_id).split("|")
    if len(parts) != 5:
        return {"run_id": run_id}
    return {
        "run_id": run_id,
        "mode": parts[0],
        "scope": parts[1],
        "roi_prior_mu": parts[2],
        "roi_prior_sigma": parts[3],
        "roi_prior_dist": parts[4],
    }


def _split_flagged(raw_value) -> list[str]:
    if pd.isna(raw_value):
        return []
    items = []
    for token in str(raw_value).split(","):
        token = token.strip()
        if token:
            items.append(token)
    return items


def _aggregate_runs(df: pd.DataFrame, score_abs_col: str, score_signed_col: str | None) -> pd.DataFrame:
    rows = []
    grouped = df.groupby("run_id", dropna=False)
    for run_id, group in grouped:
        first = group.iloc[0]
        row = {
            "run_id": run_id,
            "qc_status_code": first.get("qc_status_code"),
            "qc_summary_short": first.get("qc_summary_short"),
            "qc_primary_review_check": first.get("qc_primary_review_check"),
            "qc_flagged_channels": first.get("qc_flagged_channels"),
            "score_abs": pd.to_numeric(group[score_abs_col], errors="coerce").fillna(0).sum(),
        }
        if score_signed_col and score_signed_col in group.columns:
            row["score_signed"] = pd.to_numeric(group[score_signed_col], errors="coerce").fillna(0).sum()
        rows.append({**row, **_parse_run_id(run_id)})
    return pd.DataFrame(rows)


def _print_recommendation(label: str, row: pd.Series | None, score_abs_col: str, score_signed_col: str | None) -> None:
    print(label)
    if row is None:
        print("  none")
        return

    print(f"  run_id: {row['run_id']}")
    print(
        "  grid:"
        f" mu={row.get('roi_prior_mu')},"
        f" sigma={row.get('roi_prior_sigma')},"
        f" dist={row.get('roi_prior_dist')}"
    )
    print(f"  qc: {row.get('qc_summary_short')}")
    print(f"  score ({score_abs_col}): {float(row['score_abs']):.4f}")
    if score_signed_col and "score_signed" in row:
        print(f"  signed ({score_signed_col}): {float(row['score_signed']):.4f}")
    flagged = row.get("qc_flagged_channels")
    if pd.notna(flagged) and str(flagged).strip():
        print(f"  flagged_channels: {flagged}")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if len(args.targets) < 1:
        raise ValueError("Provide at least one target channel.")

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    targets_sorted = sorted(str(t) for t in args.targets)
    tag = _tag_for_targets(targets_sorted)
    tornado_csv = _tornado_path(project_root, tag)
    _ensure_tornado_exists(project_root, targets_sorted, tornado_csv)

    df = pd.read_csv(tornado_csv)
    if df.empty:
        raise ValueError(f"Tornado CSV is empty: {tornado_csv}")

    if not args.include_all_channels:
        df = df[df["channel"].astype(str).isin(targets_sorted)].copy()
        if df.empty:
            raise ValueError("No target-channel rows found after filtering.")

    score_abs_col, score_signed_col = _pick_score_columns(df)
    run_df = _aggregate_runs(df, score_abs_col, score_signed_col)
    non_fail_df = run_df[run_df["qc_status_code"].astype(str) != "FAIL"].copy()
    stable_df = non_fail_df[non_fail_df["qc_status_code"].astype(str) == "PASS"].copy()
    aggressive_df = non_fail_df.copy()

    stable_best = None if stable_df.empty else stable_df.sort_values("score_abs", ascending=False).iloc[0]
    aggressive_best = None if aggressive_df.empty else aggressive_df.sort_values("score_abs", ascending=False).iloc[0]

    flagged_counter: Counter[str] = Counter()
    flagged_source = non_fail_df if not non_fail_df.empty else run_df
    for value in flagged_source.get("qc_flagged_channels", pd.Series(dtype=object)).tolist():
        flagged_counter.update(_split_flagged(value))

    print(f"Target set: {','.join(targets_sorted)}")
    print(f"Tornado CSV: {tornado_csv}")
    print(f"Scoring metric: {score_abs_col}")
    if score_signed_col:
        print(f"Signed metric: {score_signed_col}")
    print()

    _print_recommendation("Best stable next test", stable_best, score_abs_col, score_signed_col)
    print()
    _print_recommendation("Best aggressive next test", aggressive_best, score_abs_col, score_signed_col)
    print()

    print("Flagged channels to consider removing next")
    if not flagged_counter:
        print("  none")
    else:
        for channel, count in flagged_counter.most_common():
            print(f"  {channel}: flagged in {count} non-fail run(s)")


if __name__ == "__main__":
    main()
