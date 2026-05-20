# Robustness Score Report (channel0,channel1,channel2,channel3,channel4)

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

- Overall robustness score: **58.51** (Medium)
- Weighting: `spend`
- Baseline prior: mu=1.000000, sigma=1.000000, dist=LogNormal
- Overall sensitivity-elasticity subscore (60%): 51.72
- Overall data-influence subscore (25%): 56.62
- Overall cross-channel subscore (15%): 88.81

## Most Fragile Channels

- channel3: overall=55.85, prior_sens=47.46, data_influence=57.51, cross_channel=86.64
- channel1: overall=59.47, prior_sens=54.02, data_influence=53.80, cross_channel=90.72
- channel0: overall=59.91, prior_sens=53.91, data_influence=55.97, cross_channel=90.50

## Most Robust Channels

- channel4: overall=61.03, prior_sens=54.83, data_influence=58.67, cross_channel=89.75
- channel2: overall=60.72, prior_sens=57.17, data_influence=51.45, cross_channel=90.39
- channel0: overall=59.91, prior_sens=53.91, data_influence=55.97, cross_channel=90.50
