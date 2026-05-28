# Robustness Score Report (google,meta,tiktok)

## Scope

- Primary scope is prior sensitivity robustness for ROI/contribution outputs under prior perturbations, conditional on the selected structural profile.
- This is a project-defined heuristic, not an official Meridian metric.
- Subscores include sensitivity elasticity (60%), data influence (25%), and cross-channel spillover (15%).

## Formula Blocks

- Sensitivity elasticity: `(Delta output / |baseline output|) / (Delta prior / |baseline prior|)`
- Near-zero baseline ROI uses contribution movement when available, otherwise log-scaled absolute delta ROI fallback.
- Fragility metrics map to 0-100 with `100 / (1 + fragility / reference_scale)`; higher is more robust.
- Data influence increases when diffuse-prior movement is low, prior-posterior distance is high, or credible-interval overlap is high.
- Cross-channel fragility uses non-self channel movement when the selected target channel's prior is perturbed.
- Structural settings are fixed context only; no adstock/structural robustness subscore is included.
- Main bands use provisional fixed thresholds on the 0-100 score: Low < 50, Medium 50-74, High >= 75.
- Relative Rank is reported separately as rank / tested channels; rank 1 is most robust within the current run.

## Overall Model Score

- Overall robustness score: **64.24** (Medium)
- Weighting: `spend`
- Baseline prior: mu=1.000000, sigma=1.000000, dist=LogNormal
- Overall sensitivity-elasticity subscore (60%): 60.79
- Overall data-influence subscore (25%): 57.05
- Overall cross-channel subscore (15%): 89.99

## Most Fragile Channels

- tiktok: overall=54.73, prior_sens=43.02, data_influence=58.45, cross_channel=95.39
- google: overall=56.08, prior_sens=47.25, data_influence=58.32, cross_channel=87.69
- meta: overall=77.02, prior_sens=83.20, data_influence=55.12, cross_channel=88.79

## Most Robust Channels

- meta: overall=77.02, prior_sens=83.20, data_influence=55.12, cross_channel=88.79
- google: overall=56.08, prior_sens=47.25, data_influence=58.32, cross_channel=87.69
- tiktok: overall=54.73, prior_sens=43.02, data_influence=58.45, cross_channel=95.39
