# src/utils.py
import numpy as np
import pandas as pd
import tensorflow_probability as tfp
from meridian.model import prior_distribution, spec

BASE_ROI_MU = 0.4
BASE_ROI_SIGMA = 0.5

def build_model_spec(channels, target_channel, roi_mu, roi_sigma=BASE_ROI_SIGMA, roi_dist="LogNormal"):
    roi_mu_vec = np.full(len(channels), BASE_ROI_MU, dtype=np.float32)
    roi_sigma_vec = np.full(len(channels), BASE_ROI_SIGMA, dtype=np.float32)

    idx = channels.index(target_channel)
    roi_mu_vec[idx] = np.float32(roi_mu)
    roi_sigma_vec[idx] = np.float32(roi_sigma)

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
