# src/utils.py
import numpy as np
import pandas as pd
import tensorflow_probability as tfp
from meridian.model import prior_distribution, spec

BASE_ROI_MU = 0.4
BASE_ROI_SIGMA = 0.5

def build_model_spec(
    channels,
    target_channel=None,
    roi_mu=None,
    roi_sigma=BASE_ROI_SIGMA,
    roi_dist="LogNormal",
    roi_prior_overrides=None, 
):
    """
    Backward compatible:
      - Single target: pass target_channel, roi_mu, roi_sigma, roi_dist
      - Multi-prior: pass roi_prior_overrides dict:
          {"meta":{"mu":..., "sigma":..., "dist":"Normal"}, "tiktok":{...}}
        NOTE: All overrides must share the same dist family (Normal vs LogNormal).
    """

    roi_mu_vec = np.full(len(channels), BASE_ROI_MU, dtype=np.float32)
    roi_sigma_vec = np.full(len(channels), BASE_ROI_SIGMA, dtype=np.float32)

    # Multi-prior mode
    if roi_prior_overrides is not None:
        dists = [v.get("dist", roi_dist) for v in roi_prior_overrides.values()]
        shared_dist = dists[0] if len(dists) > 0 else roi_dist
        if any(d != shared_dist for d in dists):
            raise ValueError(
                "Mixed dist types in roi_prior_overrides are not supported in one run. "
                "Use the same dist (all Normal or all LogNormal) for all targets."
            )

        for ch, params in roi_prior_overrides.items():
            if ch not in channels:
                raise ValueError(f"Override channel '{ch}' not in channels list.")
            idx = channels.index(ch)
            roi_mu_vec[idx] = np.float32(params["mu"])
            roi_sigma_vec[idx] = np.float32(params["sigma"])

        roi_dist = shared_dist

    # Single-target mode
    else:
        if target_channel is None or roi_mu is None:
            raise ValueError("Single-target mode requires target_channel and roi_mu.")
        idx = channels.index(target_channel)
        roi_mu_vec[idx] = np.float32(roi_mu)
        roi_sigma_vec[idx] = np.float32(roi_sigma)

    # build distribution
    if roi_dist == "LogNormal":
        roi_prior = tfp.distributions.LogNormal(
            loc=roi_mu_vec,
            scale=roi_sigma_vec,
            name="roi_m"
        )
    elif roi_dist == "Normal":
        roi_prior = tfp.distributions.Normal(
            loc=roi_mu_vec,
            scale=roi_sigma_vec,
            name="roi_m"
        )
    else:
        raise ValueError(f"Unsupported distribution type: {roi_dist}")

    prior = prior_distribution.PriorDistribution(roi_m=roi_prior)
    return spec.ModelSpec(prior=prior, enable_aks=True)

def extract_roi_mean(mmm, channels):
    idata = mmm.inference_data
    roi = idata.posterior["roi_m"]
    mean_roi = roi.mean(dim=["chain", "draw"]).values

    return pd.DataFrame({
        "channel": channels,
        "estimated_roi": mean_roi
    })