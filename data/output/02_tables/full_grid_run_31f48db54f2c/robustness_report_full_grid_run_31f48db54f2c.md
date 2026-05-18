# Robustness Score Report (amazon,beehiiv,google,liveintent,meta,moloco,snapchat,tiktok)

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

- Overall robustness score: **63.11** (Medium)
- Weighting: `spend`
- Baseline prior: mu=0.500000, sigma=0.500000, dist=LogNormal
- Overall sensitivity-elasticity subscore (60%): 65.88
- Overall data-influence subscore (25%): 38.73
- Overall cross-channel subscore (15%): 92.62

## Most Fragile Channels

- tiktok: overall=52.26, prior_sens=55.72, data_influence=22.69, cross_channel=87.67
- moloco: overall=58.73, prior_sens=59.44, data_influence=35.07, cross_channel=95.30
- liveintent: overall=59.41, prior_sens=60.12, data_influence=35.70, cross_channel=96.06

## Most Robust Channels

- beehiiv: overall=79.11, prior_sens=98.53, data_influence=21.36, cross_channel=97.66
- snapchat: overall=73.11, prior_sens=79.85, data_influence=43.30, cross_channel=95.81
- meta: overall=67.78, prior_sens=72.29, data_influence=41.53, cross_channel=93.45
