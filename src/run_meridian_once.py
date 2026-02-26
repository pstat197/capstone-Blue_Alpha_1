# src/run_meridian_once.py
import argparse
import json
import gc
import warnings
import re

import pandas as pd
import tensorflow as tf
import numpy as np
import faulthandler

from meridian.data import data_frame_input_data_builder
from meridian.model import model

from meridian.analysis.review import reviewer
from meridian.analysis import visualizer

from src.utils import build_model_spec, extract_roi_mean

faulthandler.enable()
warnings.filterwarnings("ignore")
tf.get_logger().setLevel("ERROR")


def qc_to_pass_fail(qc_text: str, status) -> str:
    """Return 'PASS'/'FAIL'/'UNKNOWN' using official status if available; otherwise parse text."""
    if status is not None:
        s = str(status).strip().upper()
        if "PASS" in s:
            return "PASS"
        if "FAIL" in s:
            return "FAIL"

    t = (qc_text or "").lower()
    if "overall status: pass" in t:
        return "PASS"
    if "overall status: fail" in t:
        return "FAIL"
    if "failed" in t or "error" in t:
        return "FAIL"
    return "UNKNOWN"


def _parse_first_float(pattern: str, text: str):
    """Return first captured float for a regex like r'R-squared\\s*=\\s*([0-9.]+)'."""
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def extract_qc_metrics_from_text(qc_text: str) -> dict:
    """
    Extract common numbers that appear in Meridian ModelReviewer text (like your screenshot),
    so we store values (not plots).
    """
    return {
        "qc_r2": _parse_first_float(r"R-squared\s*=\s*([0-9.]+)", qc_text),
        "qc_mape": _parse_first_float(r"\bMAPE\s*=\s*([0-9.]+)", qc_text),
        "qc_wmape": _parse_first_float(r"\bwMAPE\s*=\s*([0-9.]+)", qc_text),
        "qc_bayesian_ppp": _parse_first_float(r"posterior predictive p-value\s*is\s*([0-9.]+)", qc_text),
        "qc_baseline_neg_prob": _parse_first_float(r"posterior probability.*baseline.*negative\s*is\s*([0-9.]+)", qc_text),
    }


def extract_rhat_summary(mmm) -> dict:
    """
    convergence numbers.
    Best-effort: different Meridian versions expose R-hat differently.
    Returns {} if not accessible.
    """
    try:
        md = visualizer.ModelDiagnostics(mmm)

        rhat_obj = None
        for attr in ("rhat", "rhat_df", "rhat_values"):
            if hasattr(md, attr):
                rhat_obj = getattr(md, attr)
                break
        if rhat_obj is None and hasattr(md, "get_rhat"):
            rhat_obj = md.get_rhat()

        if rhat_obj is None:
            return {}

        if hasattr(rhat_obj, "values"):
            arr = np.asarray(rhat_obj.values, dtype=float).ravel()
        else:
            arr = np.asarray(rhat_obj, dtype=float).ravel()

        arr = arr[np.isfinite(arr)]
        if arr.size == 0:
            return {}

        return {
            "rhat_max": float(np.max(arr)),
            "rhat_mean": float(np.mean(arr)),
            "rhat_p95": float(np.quantile(arr, 0.95)),
            "rhat_num_gt_1p2": int(np.sum(arr > 1.2)),
        }
    except Exception:
        return {}


def extract_fit_metrics_best_effort(mmm) -> dict:
    """
    fit numbers.
    If ModelFit exposes a dataframe with actual/expected, compute MAE/RMSE/MAPE.
    Returns {} if not accessible.
    """
    try:
        mf = visualizer.ModelFit(mmm)
        if not (hasattr(mf, "df") and mf.df is not None):
            return {}

        df_fit = mf.df
        cols_lower = {c.lower(): c for c in df_fit.columns}

        a_col = cols_lower.get("actual")
        e_col = cols_lower.get("expected") or cols_lower.get("predicted") or cols_lower.get("prediction")
        if a_col is None or e_col is None:
            return {}

        actual = np.asarray(df_fit[a_col], dtype=float)
        expected = np.asarray(df_fit[e_col], dtype=float)

        mask = np.isfinite(actual) & np.isfinite(expected)
        actual = actual[mask]
        expected = expected[mask]
        if actual.size == 0:
            return {}

        resid = actual - expected
        mae = float(np.mean(np.abs(resid)))
        rmse = float(np.sqrt(np.mean(resid ** 2)))

        denom = np.where(np.abs(actual) < 1e-12, np.nan, np.abs(actual))
        mape = float(np.nanmean(np.abs(resid) / denom))

        return {"fit_mae": mae, "fit_rmse": rmse, "fit_mape": mape, "fit_n": int(actual.size)}
    except Exception:
        return {}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--channels_json", required=True)

    # multi-prior overrides
    parser.add_argument("--roi_prior_overrides_json", default=None)

    # single-target args
    parser.add_argument("--target_channel", default=None)
    parser.add_argument("--mu", type=float, default=None)
    parser.add_argument("--sigma", type=float, default=None)
    parser.add_argument("--dist", type=str, default=None)

    parser.add_argument("--out_csv", required=True)

    parser.add_argument("--n_chains", type=int, default=1)
    parser.add_argument("--n_adapt", type=int, default=100)
    parser.add_argument("--n_burnin", type=int, default=50)
    parser.add_argument("--n_keep", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)

    parser.add_argument("--baseline_mu", type=float, default=None)
    parser.add_argument("--baseline_sigma", type=float, default=None)
    parser.add_argument("--baseline_dist", type=str, default=None)

    args = parser.parse_args()
    channels = json.loads(args.channels_json)

    # determine mode
    multiprior = args.roi_prior_overrides_json is not None
    if not multiprior:
        if args.target_channel is None or args.mu is None or args.sigma is None or args.dist is None:
            raise ValueError(
                "Single-target mode requires --target_channel, --mu, --sigma, --dist "
                "OR provide --roi_prior_overrides_json for multi-prior mode."
            )

    # load data
    df = pd.read_csv(args.csv)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.rename(columns={"date": "time"})
    else:
        df["time"] = pd.to_datetime(df["time"])

    # build input_data
    builder = data_frame_input_data_builder.DataFrameInputDataBuilder(
        kpi_type="non_revenue",
        default_kpi_column="subscriptions",
    )
    builder = builder.with_kpi(df)
    builder = builder.with_media(
        df,
        media_cols=[f"{c}_impressions" for c in channels],
        media_spend_cols=[f"{c}_spend" for c in channels],
        media_channels=channels,
    )
    input_data = builder.build()

    # build spec
    if multiprior:
        overrides = json.loads(args.roi_prior_overrides_json)
        model_spec = build_model_spec(channels=channels, roi_prior_overrides=overrides)

        targets = sorted(list(overrides.keys()))
        targets_str = ",".join(targets)

        first = overrides[targets[0]]
        shared_mu = first.get("mu", None)
        shared_sigma = first.get("sigma", None)
        shared_dist = first.get("dist", None)

        prior_key = json.dumps(overrides, sort_keys=True)
    else:
        model_spec = build_model_spec(
            channels=channels,
            target_channel=args.target_channel,
            roi_mu=args.mu,
            roi_sigma=args.sigma,
            roi_dist=args.dist,
        )
        targets_str = args.target_channel
        shared_mu = args.mu
        shared_sigma = args.sigma
        shared_dist = args.dist
        prior_key = None

    # fit
    mmm = model.Meridian(input_data=input_data, model_spec=model_spec)
    mmm.sample_posterior(
        n_chains=args.n_chains,
        n_adapt=args.n_adapt,
        n_burnin=args.n_burnin,
        n_keep=args.n_keep,
        seed=args.seed,
    )

    # ModelReviewer
    qc = reviewer.ModelReviewer(mmm).run()
    qc_text = str(qc)

    qc_status = None
    qc_summary = None
    if isinstance(qc, dict):
        qc_status = qc.get("overall_status") or qc.get("Overall Status")
        qc_summary = qc.get("summary") or qc.get("Summary")
    else:
        qc_status = getattr(qc, "overall_status", None)
        qc_summary = getattr(qc, "summary", None)

    qc_pass_fail = qc_to_pass_fail(qc_text, qc_status)
    qc_metrics = extract_qc_metrics_from_text(qc_text)

    # diagnostics values
    rhat_metrics = extract_rhat_summary(mmm)
    fit_metrics = extract_fit_metrics_best_effort(mmm)

    # ROI extraction
    roi_df = extract_roi_mean(mmm, channels)

    roi_df["target_channel"] = targets_str
    roi_df["roi_prior_mu"] = (args.mu if not multiprior else shared_mu)
    roi_df["roi_prior_sigma"] = (args.sigma if not multiprior else shared_sigma)
    roi_df["roi_prior_dist"] = (args.dist if not multiprior else shared_dist)

    roi_df["roi_prior_mu"] = pd.to_numeric(roi_df["roi_prior_mu"], errors="coerce").round(6)
    roi_df["roi_prior_sigma"] = pd.to_numeric(roi_df["roi_prior_sigma"], errors="coerce").round(6)
    roi_df["roi_prior_dist"] = roi_df["roi_prior_dist"].astype(str)

    # baseline flag
    if args.baseline_mu is not None and args.baseline_sigma is not None and args.baseline_dist is not None:
        roi_df["is_baseline"] = (
            np.isclose(roi_df["roi_prior_mu"], float(args.baseline_mu))
            & np.isclose(roi_df["roi_prior_sigma"], float(args.baseline_sigma))
            & (roi_df["roi_prior_dist"] == str(args.baseline_dist))
        )
    else:
        roi_df["is_baseline"] = False

    if multiprior:
        roi_df["targets"] = targets_str
        roi_df["prior_key"] = prior_key
        roi_df["roi_prior_overrides_json"] = prior_key

    roi_df["qc_overall_status"] = qc_status
    roi_df["qc_summary"] = qc_summary
    roi_df["qc_pass_fail"] = qc_pass_fail
    roi_df["qc_text"] = qc_text
    for k, v in qc_metrics.items():
        roi_df[k] = v

    for k, v in rhat_metrics.items():
        roi_df[k] = v
    for k, v in fit_metrics.items():
        roi_df[k] = v

    roi_df.to_csv(args.out_csv, index=False)

    tf.keras.backend.clear_session()
    gc.collect()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        raise