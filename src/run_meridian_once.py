# src/run_meridian_once.py
import argparse
import json
import gc
import warnings
import re
from typing import Optional, Tuple

import pandas as pd
import tensorflow as tf
import numpy as np
import faulthandler

from meridian.data import data_frame_input_data_builder
from meridian.model import model

from meridian.analysis.review import reviewer

from src.utils import build_model_spec, extract_roi_mean

faulthandler.enable()
warnings.filterwarnings("ignore")
tf.get_logger().setLevel("ERROR")

CHECK_ORDER = [
    ("Convergence", "qc_convergence_status"),
    ("Baseline", "qc_baseline_status"),
    ("BayesianPPP", "qc_bayesianppp_status"),
    ("GoodnessOfFit", "qc_gof_status"),
    ("PriorPosteriorShift", "qc_prior_posterior_shift_status"),
    ("ROIConsistency", "qc_roi_consistency_status"),
]


def _normalize_status_token(raw_status) -> Optional[str]:
    """Normalize Meridian status values (including enum reprs like `Status.PASS`)."""
    if raw_status is None:
        return None
    if hasattr(raw_status, "name"):
        return str(raw_status.name).strip().upper()

    s = str(raw_status).strip().upper()
    if "." in s:
        s = s.split(".")[-1]

    if "REVIEW" in s:
        return "REVIEW"
    if "FAIL" in s:
        return "FAIL"
    if "PASS" in s:
        return "PASS"
    return s or None


def qc_to_pass_fail(qc_text: str, status) -> str:
    """Return `PASS`/`FAIL`/`UNKNOWN` from status first, then text fallback."""
    norm = _normalize_status_token(status)
    if norm == "FAIL":
        return "FAIL"
    if norm == "PASS":
        return "PASS"

    t = (qc_text or "").lower()
    if "overall status: fail" in t or "failed" in t or "error" in t:
        return "FAIL"
    if "overall status: pass" in t:
        return "PASS"
    return "UNKNOWN"


def qc_needs_review(summary: Optional[str], qc_text: str = "") -> bool:
    """Return True when reviewer indicates manual review is needed."""
    s = (summary or "").lower()
    t = (qc_text or "").lower()
    review_tokens = ("review is needed", "passed with reviews")
    return any(tok in s for tok in review_tokens) or any(tok in t for tok in review_tokens)


def _extract_label_value(text: str, label: str):
    """Extract a line value like `Overall Status: PASS` from review text."""
    m = re.search(rf"\b{re.escape(label)}\s*:\s*(.+)", text or "", flags=re.IGNORECASE)
    if not m:
        return None
    value = m.group(1).strip()
    return value if value else None

def normalize_qc_payload(qc) -> Tuple[str, Optional[str], Optional[str]]:
    """Return `(qc_report_full, qc_status, qc_summary)` with robust fallbacks across Meridian versions."""
    qc_report_full = str(qc or "")
    qc_status = None
    qc_summary = None

    if isinstance(qc, dict):
        qc_status = (
            qc.get("overall_status")
            or qc.get("Overall Status")
            or qc.get("status")
        )
        qc_summary = (
            qc.get("summary")
            or qc.get("Summary")
            or qc.get("summary_message")
        )
        if not qc_report_full.strip() or qc_report_full.strip().startswith("{"):
            lines = []
            if qc_status is not None:
                lines.append(f"Overall Status: {qc_status}")
            if qc_summary is not None:
                lines.append(f"Summary: {qc_summary}")
            qc_report_full = "\n".join(lines) if lines else json.dumps(qc, indent=2, sort_keys=True)
    else:
        qc_status = getattr(qc, "overall_status", None) or getattr(qc, "status", None)
        qc_summary = getattr(qc, "summary", None) or getattr(qc, "summary_message", None)

    qc_status = _normalize_status_token(qc_status) or _normalize_status_token(_extract_label_value(qc_report_full, "Overall Status"))
    qc_summary = str(qc_summary).strip() if qc_summary is not None else _extract_label_value(qc_report_full, "Summary")

    if not qc_report_full and qc_summary:
        qc_report_full = qc_summary
    elif not qc_report_full and qc_status:
        qc_report_full = f"Overall Status: {qc_status}"
    return qc_report_full, qc_status, qc_summary


def _parse_first_float(pattern: str, text: str):
    """Return first captured float for a regex like r'R-squared\\s*=\\s*([0-9.]+)'."""
    m = re.search(pattern, text or "", flags=re.IGNORECASE | re.DOTALL)
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
        "qc_r2": _parse_first_float(r"R-squared\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", qc_text),
        "qc_mape": _parse_first_float(r"\bMAPE\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", qc_text),
        "qc_wmape": _parse_first_float(r"\bwMAPE\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", qc_text),
        "qc_bayesian_ppp": _parse_first_float(r"posterior\s+predictive\s+p-value\s*(?:is|=)\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", qc_text),
        "qc_baseline_neg_prob": _parse_first_float(r"posterior\s+probability.*?baseline.*?negative\s*(?:is|=)\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", qc_text),
    }


def _extract_check_status(report_text: str, check_name: str) -> Optional[str]:
    pattern = rf"{re.escape(check_name)}\s+Check:\s*Status:\s*([A-Za-z_.]+)"
    m = re.search(pattern, report_text or "", flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    return _normalize_status_token(m.group(1))


def _extract_check_recommendation(report_text: str, check_name: str) -> Optional[str]:
    pattern = (
        rf"{re.escape(check_name)}\s+Check:\s*"
        rf"Status:\s*[A-Za-z_.]+\s*"
        rf"Recommendation:\s*(.+?)"
        rf"(?=(?:-{{10,}})|(?:[A-Za-z]+\s+Check:)|\Z)"
    )
    m = re.search(pattern, report_text or "", flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    value = " ".join(m.group(1).split())
    return value or None


def extract_check_details(report_text: str) -> dict:
    details = {}
    for check_name, status_col in CHECK_ORDER:
        details[status_col] = _extract_check_status(report_text, check_name)
    return details


def _dedupe_preserve_order(values) -> list:
    seen = set()
    out = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def extract_flagged_channels(text: Optional[str]) -> str:
    matches = re.findall(r"`([^`]+)`", text or "")
    channels = []
    for match in matches:
        for token in match.split(","):
            token = token.strip()
            if token:
                channels.append(token)
    return ",".join(_dedupe_preserve_order(channels))


def derive_qc_rollup(qc_status: Optional[str], needs_review: bool, check_details: dict, report_text: str) -> dict:
    overall = _normalize_status_token(qc_status)
    if overall == "FAIL":
        code = "FAIL"
        severity = 2
    elif needs_review:
        code = "REVIEW"
        severity = 1
    elif overall == "PASS":
        code = "PASS"
        severity = 0
    else:
        code = overall or "UNKNOWN"
        severity = 3

    primary_check = None
    for check_name, status_col in CHECK_ORDER:
        status = _normalize_status_token(check_details.get(status_col))
        if status and status != "PASS":
            primary_check = check_name
            break

    summary_short = code
    if primary_check:
        summary_short = f"{code}:{primary_check}"

    review_reason = _extract_check_recommendation(report_text, primary_check) if primary_check else None
    flagged_channels = extract_flagged_channels(review_reason)

    return {
        "qc_status_code": code,
        "qc_severity_rank": severity,
        "qc_summary_short": summary_short,
        "qc_primary_review_check": primary_check,
        "qc_flagged_channels": flagged_channels,
        "qc_review_reason": review_reason,
    }


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

    parser.add_argument("--out_run_csv", default=None)
    parser.add_argument("--out_roi_csv", default=None)
    parser.add_argument("--out_csv", default=None)

    parser.add_argument("--n_chains", type=int, default=1)
    parser.add_argument("--n_adapt", type=int, default=100)
    parser.add_argument("--n_burnin", type=int, default=50)
    parser.add_argument("--n_keep", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)

    parser.add_argument("--baseline_mu", type=float, default=None)
    parser.add_argument("--baseline_sigma", type=float, default=None)
    parser.add_argument("--baseline_dist", type=str, default=None)

    args = parser.parse_args()
    if args.out_roi_csv is None:
        if args.out_csv is None:
            raise ValueError("Provide --out_roi_csv (preferred) or legacy --out_csv.")
        args.out_roi_csv = args.out_csv
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
    qc_report_full, qc_status, qc_summary = normalize_qc_payload(qc)

    qc_pass_fail = qc_to_pass_fail(qc_report_full, qc_status)
    review_needed = qc_needs_review(qc_summary, qc_report_full)
    qc_metrics = extract_qc_metrics_from_text(qc_report_full)
    check_details = extract_check_details(qc_report_full)
    qc_rollup = derive_qc_rollup(qc_status, review_needed, check_details, qc_report_full)

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
    roi_df["qc_needs_review"] = review_needed
    roi_df["qc_text"] = qc_report_full
    for k, v in qc_metrics.items():
        roi_df[k] = v

    roi_df.to_csv(args.out_roi_csv, index=False)

    if args.baseline_mu is not None and args.baseline_sigma is not None and args.baseline_dist is not None:
        is_baseline = (
            np.isclose(float(shared_mu), float(args.baseline_mu))
            and np.isclose(float(shared_sigma), float(args.baseline_sigma))
            and str(shared_dist) == str(args.baseline_dist)
        )
    else:
        is_baseline = False

    run_row = {
        "target_channel": targets_str,
        "roi_prior_mu": round(float(shared_mu), 6) if shared_mu is not None else None,
        "roi_prior_sigma": round(float(shared_sigma), 6) if shared_sigma is not None else None,
        "roi_prior_dist": str(shared_dist) if shared_dist is not None else None,
        "is_baseline": bool(is_baseline),
        "qc_status_code": qc_rollup["qc_status_code"],
        "qc_severity_rank": qc_rollup["qc_severity_rank"],
        "qc_needs_review": bool(review_needed),
        "qc_summary_short": qc_rollup["qc_summary_short"],
        "qc_primary_review_check": qc_rollup["qc_primary_review_check"],
        "qc_flagged_channels": qc_rollup["qc_flagged_channels"],
        "qc_review_reason": qc_rollup["qc_review_reason"],
        "qc_convergence_status": check_details.get("qc_convergence_status"),
        "qc_baseline_status": check_details.get("qc_baseline_status"),
        "qc_bayesianppp_status": check_details.get("qc_bayesianppp_status"),
        "qc_gof_status": check_details.get("qc_gof_status"),
        "qc_prior_posterior_shift_status": check_details.get("qc_prior_posterior_shift_status"),
        "qc_roi_consistency_status": check_details.get("qc_roi_consistency_status"),
        "qc_r2": qc_metrics.get("qc_r2"),
        "qc_mape": qc_metrics.get("qc_mape"),
        "qc_wmape": qc_metrics.get("qc_wmape"),
        "qc_bayesian_ppp": qc_metrics.get("qc_bayesian_ppp"),
        "qc_baseline_neg_prob": qc_metrics.get("qc_baseline_neg_prob"),
        "qc_report_full": qc_report_full,
    }
    if multiprior:
        run_row["targets"] = targets_str
        run_row["prior_key"] = prior_key

    run_df = pd.DataFrame([run_row])
    if args.out_run_csv:
        run_df.to_csv(args.out_run_csv, index=False)

    tf.keras.backend.clear_session()
    gc.collect()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        raise
