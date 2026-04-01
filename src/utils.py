# src/utils.py
import numpy as np
import pandas as pd
import tensorflow_probability as tfp
from meridian.model import prior_distribution, spec

BASE_ROI_MU = 0.4
BASE_ROI_SIGMA = 0.5
_ALLOWED_DECAYS = {"geometric", "binomial"}


def _natural_to_lognormal_params(mu_vec: np.ndarray, sigma_vec: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Convert natural-scale mean/std into log-space loc/scale for LogNormal."""
    mu_safe = np.maximum(mu_vec.astype(np.float32), np.float32(1e-8))
    sigma_safe = np.maximum(sigma_vec.astype(np.float32), np.float32(1e-8))
    log_scale_sq = np.log1p((sigma_safe ** 2) / (mu_safe ** 2)).astype(np.float32)
    return (np.log(mu_safe) - 0.5 * log_scale_sq).astype(np.float32), np.sqrt(log_scale_sq).astype(np.float32)


def _fixed_uniform(value: float, name: str, *, lower: float, upper: float | None = None):
    """Approximate a fixed value with a narrow Uniform prior on a bounded range."""
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
    """Build Meridian ModelSpec with ROI prior overrides and optional structural overrides."""
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
    alpha_m = s.get("alpha_m")
    ec_m = s.get("ec_m")
    slope_m = s.get("slope_m")
    if alpha_m is not None:
        prior_kwargs["alpha_m"] = _fixed_uniform(float(alpha_m), "alpha_m", lower=0.0, upper=1.0)
    if ec_m is not None:
        prior_kwargs["ec_m"] = _fixed_uniform(float(ec_m), "ec_m", lower=1e-6)
    if slope_m is not None:
        prior_kwargs["slope_m"] = _fixed_uniform(float(slope_m), "slope_m", lower=1e-6)

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
