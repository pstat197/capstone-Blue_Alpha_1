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
import platformdirs
import tensorflow as tf

# Keep ArviZ cache in-project when user-level cache paths are not writable.
_cache_root = Path(os.environ.get("BLUEALPHA_CACHE_DIR", Path.cwd() / ".cache")).resolve()
(_cache_root / "arviz").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(_cache_root))
os.environ.setdefault("ARVIZ_HOME", str(_cache_root / "arviz"))
os.environ.setdefault("LOCALAPPDATA", str(_cache_root))
os.environ.setdefault("APPDATA", str(_cache_root))


def _workspace_user_cache_dir(
    appname: Optional[str] = None,
    appauthor: Optional[str] = None,
    version: Optional[str] = None,
    opinion: bool = True,
    ensure_exists: bool = False,
) -> str:
    base = (_cache_root / "platformdirs").resolve()
    parts = [p for p in [appauthor, appname, version] if p]
    path = base.joinpath(*parts) if parts else base
    if ensure_exists:
        path.mkdir(parents=True, exist_ok=True)
    return str(path)


platformdirs.user_cache_dir = _workspace_user_cache_dir

from meridian.analysis.review import reviewer
from meridian.data import data_frame_input_data_builder
from meridian.model import model, prior_distribution, spec
import tensorflow_probability as tfp

# ---------------------------------------------------------------------------
# Meridian ModelSpec construction (inlined from former meridian_spec.py)
# ---------------------------------------------------------------------------

BASE_ROI_MU = 0.4
BASE_ROI_SIGMA = 0.5
_ALLOWED_DECAYS = {"geometric", "binomial"}


def _natural_to_lognormal_params(mu_vec: np.ndarray, sigma_vec: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mu_safe = np.maximum(mu_vec.astype(np.float32), np.float32(1e-8))
    sigma_safe = np.maximum(sigma_vec.astype(np.float32), np.float32(1e-8))
    log_scale_sq = np.log1p((sigma_safe ** 2) / (mu_safe ** 2)).astype(np.float32)
    return (np.log(mu_safe) - 0.5 * log_scale_sq).astype(np.float32), np.sqrt(log_scale_sq).astype(np.float32)


def _fixed_uniform(value: float, name: str, *, lower: float, upper: float | None = None):
    v = float(value)
    if upper is not None:
        eps = max((upper - lower) * 1e-4, 1e-6)
        v = min(max(v, lower + eps), upper - eps)
        lo, hi = max(lower, v - eps), min(upper, v + eps)
    else:
        v = max(v, lower)
        eps = max(abs(v) * 1e-4, 1e-6)
        lo, hi = max(lower, v - eps), v + eps
    if hi <= lo:
        hi = lo + 1e-6
    return tfp.distributions.Uniform(low=np.float32(lo), high=np.float32(hi), name=name)


def _build_roi_prior(roi_dist: str, roi_mu_vec: np.ndarray, roi_sigma_vec: np.ndarray):
    if roi_dist == "LogNormal":
        log_loc, log_scale = _natural_to_lognormal_params(roi_mu_vec, roi_sigma_vec)
        return tfp.distributions.LogNormal(loc=log_loc, scale=log_scale, name="roi_m")
    if roi_dist == "Normal":
        return tfp.distributions.Normal(loc=roi_mu_vec, scale=roi_sigma_vec, name="roi_m")
    raise ValueError(f"Unsupported distribution type: {roi_dist}")


def build_model_spec(
    channels,
    target_channel=None,
    roi_mu=None,
    roi_sigma=BASE_ROI_SIGMA,
    roi_dist="LogNormal",
    roi_prior_overrides=None,
    structural_overrides=None,
):
    roi_mu_vec = np.full(len(channels), BASE_ROI_MU, dtype=np.float32)
    roi_sigma_vec = np.full(len(channels), BASE_ROI_SIGMA, dtype=np.float32)

    if roi_prior_overrides is not None:
        shared_dist = None
        for ch, params in roi_prior_overrides.items():
            if ch not in channels:
                raise ValueError(f"Override channel '{ch}' not in channels list.")
            d = str(params.get("dist", roi_dist))
            if shared_dist is None:
                shared_dist = d
            elif d != shared_dist:
                raise ValueError(
                    "Mixed dist types in roi_prior_overrides are not supported in one run. "
                    "Use the same dist (all Normal or all LogNormal) for all targets."
                )
            idx = channels.index(ch)
            roi_mu_vec[idx] = np.float32(params["mu"])
            roi_sigma_vec[idx] = np.float32(params["sigma"])
        roi_dist = shared_dist or roi_dist
    else:
        if target_channel is None or roi_mu is None:
            raise ValueError("Single-target mode requires target_channel and roi_mu.")
        idx = channels.index(target_channel)
        roi_mu_vec[idx] = np.float32(roi_mu)
        roi_sigma_vec[idx] = np.float32(roi_sigma)

    prior_kwargs = {"roi_m": _build_roi_prior(roi_dist, roi_mu_vec, roi_sigma_vec)}
    model_spec_kwargs = {"enable_aks": True}

    s = structural_overrides or {}
    if s.get("alpha_m") is not None:
        prior_kwargs["alpha_m"] = _fixed_uniform(float(s["alpha_m"]), "alpha_m", lower=0.0, upper=1.0)
    if s.get("ec_m") is not None:
        prior_kwargs["ec_m"] = _fixed_uniform(float(s["ec_m"]), "ec_m", lower=1e-6)
    if s.get("slope_m") is not None:
        prior_kwargs["slope_m"] = _fixed_uniform(float(s["slope_m"]), "slope_m", lower=1e-6)
    if s.get("max_lag") is not None:
        model_spec_kwargs["max_lag"] = int(s["max_lag"])
    if s.get("adstock_decay_spec") is not None:
        decay = str(s["adstock_decay_spec"]).strip().lower()
        if decay not in _ALLOWED_DECAYS:
            raise ValueError("adstock_decay_spec must be 'geometric' or 'binomial'.")
        model_spec_kwargs["adstock_decay_spec"] = decay

    return spec.ModelSpec(prior=prior_distribution.PriorDistribution(**prior_kwargs), **model_spec_kwargs)


def extract_roi_mean(mmm, channels):
    mean_roi = mmm.inference_data.posterior["roi_m"].mean(dim=["chain", "draw"]).values
    return pd.DataFrame({"channel": channels, "estimated_roi": mean_roi})

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
    parser.add_argument("--kpi_col", default="subscriptions")
    parser.add_argument("--time_col", default="date")
    parser.add_argument("--geo_col", default=None)
    parser.add_argument("--population_col", default=None)
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


def _first_present_column(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    existing = {str(c).strip().lower(): c for c in df.columns}
    for raw in candidates:
        key = str(raw).strip().lower()
        if key in existing:
            return existing[key]
    return None


def _resolve_time_column(df: pd.DataFrame, requested_time_col: Optional[str]) -> str:
    if requested_time_col and requested_time_col in df.columns:
        return requested_time_col
    fallback = _first_present_column(df, ["time", "date"])
    if fallback is None:
        raise ValueError(
            "Input CSV is missing a valid time column. "
            "Provide --time_col or include one of: time, date."
        )
    return fallback


def _resolve_geo_column(df: pd.DataFrame, requested_geo_col: Optional[str]) -> Optional[str]:
    if requested_geo_col:
        if requested_geo_col not in df.columns:
            raise ValueError(f"Configured geo column '{requested_geo_col}' not found in input CSV.")
        return requested_geo_col
    return _first_present_column(df, ["geo", "region", "state", "dma", "market", "country"])


def _resolve_population_column(df: pd.DataFrame, requested_population_col: Optional[str]) -> Optional[str]:
    if requested_population_col:
        if requested_population_col not in df.columns:
            raise ValueError(f"Configured population column '{requested_population_col}' not found in input CSV.")
        return requested_population_col
    return _first_present_column(df, ["population", "pop", "population_total"])


def _load_input_data(
    csv_path: str,
    channels: list[str],
    *,
    kpi_col: str,
    time_col: Optional[str],
    geo_col: Optional[str],
    population_col: Optional[str],
):
    df = pd.read_csv(csv_path)
    resolved_time_col = _resolve_time_column(df, time_col)
    resolved_geo_col = _resolve_geo_column(df, geo_col)
    resolved_population_col = _resolve_population_column(df, population_col)

    df[resolved_time_col] = pd.to_datetime(df[resolved_time_col])

    builder = data_frame_input_data_builder.DataFrameInputDataBuilder(
        kpi_type="non_revenue",
        default_kpi_column=kpi_col,
        default_time_column=resolved_time_col,
        default_geo_column=(resolved_geo_col or "geo"),
    )
    builder = builder.with_kpi(
        df,
        kpi_col=kpi_col,
        time_col=resolved_time_col,
        geo_col=resolved_geo_col,
    )
    builder = builder.with_media(
        df,
        media_cols=[f"{c}_impressions" for c in channels],
        media_spend_cols=[f"{c}_spend" for c in channels],
        media_channels=channels,
        time_col=resolved_time_col,
        geo_col=resolved_geo_col,
    )
    if resolved_geo_col and resolved_population_col:
        builder = builder.with_population(
            df,
            population_col=resolved_population_col,
            geo_col=resolved_geo_col,
        )
    data_profile = {
        "data_granularity": "geo" if resolved_geo_col else "national",
        "data_time_col": resolved_time_col,
        "data_geo_col": resolved_geo_col,
        "data_population_col": resolved_population_col,
        "data_n_rows": int(len(df)),
        "data_n_time_periods": int(df[resolved_time_col].nunique(dropna=True)),
        "data_n_geos": int(df[resolved_geo_col].nunique(dropna=True)) if resolved_geo_col else 1,
    }
    return builder.build(), data_profile


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

    input_data, data_profile = _load_input_data(
        args.csv,
        channels,
        kpi_col=str(args.kpi_col),
        time_col=(None if args.time_col is None else str(args.time_col)),
        geo_col=(None if args.geo_col is None else str(args.geo_col)),
        population_col=(None if args.population_col is None else str(args.population_col)),
    )
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
        "data_granularity": data_profile.get("data_granularity"),
        "data_time_col": data_profile.get("data_time_col"),
        "data_geo_col": data_profile.get("data_geo_col"),
        "data_population_col": data_profile.get("data_population_col"),
        "data_n_rows": data_profile.get("data_n_rows"),
        "data_n_time_periods": data_profile.get("data_n_time_periods"),
        "data_n_geos": data_profile.get("data_n_geos"),
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
