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

- Overall robustness score: **51.33** (Medium)
- Weighting: `spend`
- Baseline prior: mu=1.000000, sigma=1.000000, dist=LogNormal
- Overall sensitivity-elasticity subscore (60%): 47.73
- Overall data-influence subscore (25%): 37.47
- Overall cross-channel subscore (15%): 88.87

## Most Fragile Channels

- tiktok: overall=47.61, prior_sens=47.85, data_influence=21.18, cross_channel=90.74
- google: overall=50.51, prior_sens=44.45, data_influence=42.77, cross_channel=87.65
- snapchat: overall=52.72, prior_sens=51.60, data_influence=33.34, cross_channel=89.50

## Most Robust Channels

- moloco: overall=55.83, prior_sens=56.78, data_influence=32.38, cross_channel=91.15
- beehiiv: overall=55.42, prior_sens=55.37, data_influence=33.14, cross_channel=92.74
- amazon: overall=54.78, prior_sens=54.32, data_influence=33.21, cross_channel=92.55
