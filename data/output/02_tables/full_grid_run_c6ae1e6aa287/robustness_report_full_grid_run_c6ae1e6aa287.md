# Robustness Score Report (amazon,beehiiv,liveintent,meta,moloco,tiktok)

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

- Overall robustness score: **55.96** (Medium)
- Weighting: `spend`
- Baseline prior: mu=0.500000, sigma=0.500000, dist=LogNormal
- Overall sensitivity-elasticity subscore (60%): 64.09
- Overall data-influence subscore (25%): 29.80
- Overall cross-channel subscore (15%): 67.04

## Most Fragile Channels

- tiktok: overall=51.07, prior_sens=55.98, data_influence=16.10, cross_channel=89.75
- liveintent: overall=51.75, prior_sens=60.63, data_influence=35.30, cross_channel=43.63
- amazon: overall=53.05, prior_sens=65.15, data_influence=29.52, cross_channel=43.87

## Most Robust Channels

- beehiiv: overall=78.81, prior_sens=98.68, data_influence=20.33, cross_channel=96.81
- meta: overall=61.53, prior_sens=69.42, data_influence=47.11, cross_channel=54.00
- moloco: overall=55.73, prior_sens=65.45, data_influence=39.56, cross_channel=43.83
