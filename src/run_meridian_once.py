# src/run_meridian_once.py
import argparse
import faulthandler
import gc
import json
import os
import re
import warnings
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import tensorflow as tf

# Keep ArviZ cache in-project when user-level cache paths are not writable.
_cache_root = Path(os.environ.get("BLUEALPHA_CACHE_DIR", Path.cwd() / ".cache")).resolve()
(_cache_root / "arviz").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(_cache_root))
os.environ.setdefault("ARVIZ_HOME", str(_cache_root / "arviz"))
os.environ.setdefault("LOCALAPPDATA", str(_cache_root))
os.environ.setdefault("APPDATA", str(_cache_root))

from meridian.analysis.review import reviewer
from meridian.data import data_frame_input_data_builder
from meridian.model import model

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

QC_METRIC_PATTERNS = {
    "qc_r2": r"R-squared\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)",
    "qc_mape": r"\bMAPE\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)",
    "qc_wmape": r"\bwMAPE\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)",
    "qc_bayesian_ppp": r"posterior\s+predictive\s+p-value\s*(?:is|=)\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)",
    "qc_baseline_neg_prob": r"posterior\s+probability.*?baseline.*?negative\s*(?:is|=)\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)",
}

STRUCT_DEFAULTS = {
    "alpha_m": None,
    "ec_m": None,
    "slope_m": 1.0,
    "max_lag": 8,
    "adstock_decay_spec": "geometric",
}


def _normalize_status_token(raw_status) -> Optional[str]:
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
    norm = _normalize_status_token(status)
    if norm in {"FAIL", "PASS"}:
        return norm
    t = (qc_text or "").lower()
    if "overall status: fail" in t or "failed" in t or "error" in t:
        return "FAIL"
    if "overall status: pass" in t:
        return "PASS"
    return "UNKNOWN"


def qc_needs_review(summary: Optional[str], qc_text: str = "") -> bool:
    s = (summary or "").lower()
    t = (qc_text or "").lower()
    review_tokens = ("review is needed", "passed with reviews")
    return any(tok in s for tok in review_tokens) or any(tok in t for tok in review_tokens)


def _extract_label_value(text: str, label: str):
    m = re.search(rf"\b{re.escape(label)}\s*:\s*(.+)", text or "", flags=re.IGNORECASE)
    return m.group(1).strip() if m else None


def normalize_qc_payload(qc) -> Tuple[str, Optional[str], Optional[str]]:
    qc_report_full = str(qc or "")
    qc_status = None
    qc_summary = None

    if isinstance(qc, dict):
        qc_status = qc.get("overall_status") or qc.get("Overall Status") or qc.get("status")
        qc_summary = qc.get("summary") or qc.get("Summary") or qc.get("summary_message")
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
    m = re.search(pattern, text or "", flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def extract_qc_metrics_from_text(qc_text: str) -> dict:
    return {k: _parse_first_float(p, qc_text) for k, p in QC_METRIC_PATTERNS.items()}


def _extract_check_status(report_text: str, check_name: str) -> Optional[str]:
    pattern = rf"{re.escape(check_name)}\s+Check:\s*Status:\s*([A-Za-z_.]+)"
    m = re.search(pattern, report_text or "", flags=re.IGNORECASE | re.DOTALL)
    return _normalize_status_token(m.group(1)) if m else None


def _extract_check_recommendation(report_text: str, check_name: str) -> Optional[str]:
    pattern = (
        rf"{re.escape(check_name)}\s+Check:\s*"
        rf"Status:\s*[A-Za-z_.]+\s*"
        rf"Recommendation:\s*(.+?)"
        rf"(?=(?:-{{10,}})|(?:[A-Za-z]+\s+Check:)|\Z)"
    )
    m = re.search(pattern, report_text or "", flags=re.IGNORECASE | re.DOTALL)
    return " ".join(m.group(1).split()) if m else None


def extract_check_details(report_text: str) -> dict:
    return {status_col: _extract_check_status(report_text, check_name) for check_name, status_col in CHECK_ORDER}


def _dedupe_preserve_order(values) -> list:
    seen, out = set(), []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def extract_flagged_channels(text: Optional[str]) -> str:
    matches = re.findall(r"`([^`]+)`", text or "")
    channels = []
    for match in matches:
        channels.extend(tok.strip() for tok in match.split(",") if tok.strip())
    return ",".join(_dedupe_preserve_order(channels))


def derive_qc_rollup(qc_status: Optional[str], needs_review: bool, check_details: dict, report_text: str) -> dict:
    overall = _normalize_status_token(qc_status)
    if overall == "FAIL":
        code, severity = "FAIL", 2
    elif needs_review:
        code, severity = "REVIEW", 1
    elif overall == "PASS":
        code, severity = "PASS", 0
    else:
        code, severity = overall or "UNKNOWN", 3

    primary_check = next(
        (
            check_name
            for check_name, status_col in CHECK_ORDER
            if (st := _normalize_status_token(check_details.get(status_col))) and st != "PASS"
        ),
        None,
    )
    summary_short = f"{code}:{primary_check}" if primary_check else code
    review_reason = _extract_check_recommendation(report_text, primary_check) if primary_check else None

    return {
        "qc_status_code": code,
        "qc_severity_rank": severity,
        "qc_summary_short": summary_short,
        "qc_primary_review_check": primary_check,
        "qc_flagged_channels": extract_flagged_channels(review_reason),
        "qc_review_reason": review_reason,
    }


def _normalize_structural_overrides(overrides: Optional[dict]) -> dict:
    raw = {**STRUCT_DEFAULTS, **(overrides or {})}
    return {
        "alpha_m": None if raw["alpha_m"] is None else round(float(raw["alpha_m"]), 6),
        "ec_m": None if raw["ec_m"] is None else round(float(raw["ec_m"]), 6),
        "slope_m": round(float(raw["slope_m"]), 6),
        "max_lag": int(raw["max_lag"]),
        "adstock_decay_spec": str(raw["adstock_decay_spec"]).strip().lower(),
    }


def _is_baseline_structural(current: dict, baseline: Optional[dict]) -> bool:
    if baseline is None:
        return True

    for key in ("alpha_m", "ec_m"):
        cur, base = current.get(key), baseline.get(key)
        if base is None and cur is not None:
            return False
        if base is not None and (cur is None or not np.isclose(float(cur), float(base))):
            return False

    if not np.isclose(float(current.get("slope_m", 1.0)), float(baseline.get("slope_m", 1.0))):
        return False
    if int(current.get("max_lag", 8)) != int(baseline.get("max_lag", 8)):
        return False
    return str(current.get("adstock_decay_spec", "geometric")) == str(baseline.get("adstock_decay_spec", "geometric"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    parser.add_argument("--csv", required=True)
    parser.add_argument("--channels_json", required=True)

    for name in ["--roi_prior_overrides_json", "--structural_overrides_json", "--prior_key"]:
        parser.add_argument(name, default=None)

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
    parser.add_argument("--baseline_structural_overrides_json", default=None)
    return parser


def _load_input_data(csv_path: str, channels: list[str]):
    df = pd.read_csv(csv_path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.rename(columns={"date": "time"})
    else:
        df["time"] = pd.to_datetime(df["time"])

    builder = data_frame_input_data_builder.DataFrameInputDataBuilder(
        kpi_type="non_revenue",
        default_kpi_column="subscriptions",
    )
    return (
        builder.with_kpi(df)
        .with_media(
            df,
            media_cols=[f"{c}_impressions" for c in channels],
            media_spend_cols=[f"{c}_spend" for c in channels],
            media_channels=channels,
        )
        .build()
    )


def _resolve_mode(args, channels: list[str], normalized_structural: dict) -> dict:
    multiprior = args.roi_prior_overrides_json is not None
    if not multiprior and any(v is None for v in [args.target_channel, args.mu, args.sigma, args.dist]):
        raise ValueError(
            "Single-target mode requires --target_channel, --mu, --sigma, --dist "
            "OR provide --roi_prior_overrides_json for multi-prior mode."
        )

    if multiprior:
        overrides = json.loads(args.roi_prior_overrides_json)
        model_spec = build_model_spec(channels=channels, roi_prior_overrides=overrides, structural_overrides=normalized_structural)
        targets = sorted(overrides.keys())
        first = overrides[targets[0]]
        return {
            "multiprior": True,
            "overrides": overrides,
            "model_spec": model_spec,
            "targets_str": ",".join(targets),
            "shared_mu": first.get("mu"),
            "shared_sigma": first.get("sigma"),
            "shared_dist": first.get("dist"),
            "prior_key": args.prior_key or json.dumps(overrides, sort_keys=True),
        }

    return {
        "multiprior": False,
        "overrides": None,
        "model_spec": build_model_spec(
            channels=channels,
            target_channel=args.target_channel,
            roi_mu=args.mu,
            roi_sigma=args.sigma,
            roi_dist=args.dist,
            structural_overrides=normalized_structural,
        ),
        "targets_str": args.target_channel,
        "shared_mu": args.mu,
        "shared_sigma": args.sigma,
        "shared_dist": args.dist,
        "prior_key": args.prior_key,
    }


def _round_or_none(v):
    return None if v is None else round(float(v), 6)


def main():
    args = _build_parser().parse_args()
    if args.out_roi_csv is None:
        if args.out_csv is None:
            raise ValueError("Provide --out_roi_csv (preferred) or legacy --out_csv.")
        args.out_roi_csv = args.out_csv

    channels = json.loads(args.channels_json)
    normalized_structural = _normalize_structural_overrides(json.loads(args.structural_overrides_json) if args.structural_overrides_json else None)
    baseline_structural = _normalize_structural_overrides(json.loads(args.baseline_structural_overrides_json)) if args.baseline_structural_overrides_json else None

    input_data = _load_input_data(args.csv, channels)
    mode = _resolve_mode(args, channels, normalized_structural)

    mmm = model.Meridian(input_data=input_data, model_spec=mode["model_spec"])
    mmm.sample_posterior(
        n_chains=args.n_chains,
        n_adapt=args.n_adapt,
        n_burnin=args.n_burnin,
        n_keep=args.n_keep,
        seed=args.seed,
    )

    qc = reviewer.ModelReviewer(mmm).run()
    qc_report_full, qc_status, qc_summary = normalize_qc_payload(qc)
    review_needed = qc_needs_review(qc_summary, qc_report_full)
    qc_metrics = extract_qc_metrics_from_text(qc_report_full)
    check_details = extract_check_details(qc_report_full)
    qc_rollup = derive_qc_rollup(qc_status, review_needed, check_details, qc_report_full)

    shared_mu = mode["shared_mu"]
    shared_sigma = mode["shared_sigma"]
    shared_dist = mode["shared_dist"]
    shared_alpha = normalized_structural["alpha_m"]
    shared_ec = normalized_structural["ec_m"]
    shared_slope = normalized_structural["slope_m"]
    shared_max_lag = normalized_structural["max_lag"]
    shared_decay = normalized_structural["adstock_decay_spec"]

    roi_df = extract_roi_mean(mmm, channels).assign(
        target_channel=mode["targets_str"],
        roi_prior_mu=(args.mu if not mode["multiprior"] else shared_mu),
        roi_prior_sigma=(args.sigma if not mode["multiprior"] else shared_sigma),
        roi_prior_dist=(args.dist if not mode["multiprior"] else shared_dist),
        adstock_alpha_m=shared_alpha,
        saturation_ec_m=shared_ec,
        saturation_slope_m=shared_slope,
        max_lag=shared_max_lag,
        adstock_decay_spec=shared_decay,
    )

    for col in ["roi_prior_mu", "roi_prior_sigma", "adstock_alpha_m", "saturation_ec_m", "saturation_slope_m", "max_lag"]:
        roi_df[col] = pd.to_numeric(roi_df[col], errors="coerce").round(6)
    for col in ["roi_prior_dist", "adstock_decay_spec"]:
        roi_df[col] = roi_df[col].astype(str)

    has_prior_baseline = all(v is not None for v in [args.baseline_mu, args.baseline_sigma, args.baseline_dist])
    if has_prior_baseline:
        prior_baseline_mask = (
            np.isclose(roi_df["roi_prior_mu"], float(args.baseline_mu))
            & np.isclose(roi_df["roi_prior_sigma"], float(args.baseline_sigma))
            & (roi_df["roi_prior_dist"] == str(args.baseline_dist))
        )
        roi_df["is_baseline"] = prior_baseline_mask & _is_baseline_structural(normalized_structural, baseline_structural)
    else:
        roi_df["is_baseline"] = False

    if mode["multiprior"]:
        roi_df["targets"] = mode["targets_str"]
        roi_df["prior_key"] = mode["prior_key"]
        roi_df["roi_prior_overrides_json"] = json.dumps(mode["overrides"], sort_keys=True)
        roi_df["structural_overrides_json"] = json.dumps(normalized_structural, sort_keys=True)

    roi_df["qc_overall_status"] = qc_status
    roi_df["qc_summary"] = qc_summary
    roi_df["qc_pass_fail"] = qc_to_pass_fail(qc_report_full, qc_status)
    roi_df["qc_needs_review"] = review_needed
    roi_df["qc_text"] = qc_report_full
    for k, v in qc_metrics.items():
        roi_df[k] = v

    roi_df.to_csv(args.out_roi_csv, index=False)

    is_baseline = False
    if has_prior_baseline:
        prior_is_baseline = (
            np.isclose(float(shared_mu), float(args.baseline_mu))
            and np.isclose(float(shared_sigma), float(args.baseline_sigma))
            and str(shared_dist) == str(args.baseline_dist)
        )
        is_baseline = bool(prior_is_baseline and _is_baseline_structural(normalized_structural, baseline_structural))

    run_row = {
        "target_channel": mode["targets_str"],
        "roi_prior_mu": _round_or_none(shared_mu),
        "roi_prior_sigma": _round_or_none(shared_sigma),
        "roi_prior_dist": str(shared_dist) if shared_dist is not None else None,
        "adstock_alpha_m": shared_alpha,
        "saturation_ec_m": shared_ec,
        "saturation_slope_m": shared_slope,
        "max_lag": shared_max_lag,
        "adstock_decay_spec": shared_decay,
        "is_baseline": is_baseline,
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
    if mode["multiprior"]:
        run_row["targets"] = mode["targets_str"]
        run_row["prior_key"] = mode["prior_key"]

    if args.out_run_csv:
        pd.DataFrame([run_row]).to_csv(args.out_run_csv, index=False)

    tf.keras.backend.clear_session()
    gc.collect()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        raise
