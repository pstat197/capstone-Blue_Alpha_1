# Robustness Score Report (amazon,beehiiv,google,meta,snapchat,tiktok)

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

- Overall robustness score: **58.71** (Medium)
- Weighting: `spend`
- Baseline prior: mu=1.000000, sigma=1.000000, dist=LogNormal
- Overall sensitivity-elasticity subscore (60%): 54.42
- Overall data-influence subscore (25%): 49.19
- Overall cross-channel subscore (15%): 91.75

## Most Fragile Channels

- google: overall=54.15, prior_sens=46.31, data_influence=51.30, cross_channel=90.22
- beehiiv: overall=55.46, prior_sens=60.03, data_influence=21.70, cross_channel=93.46
- amazon: overall=58.78, prior_sens=65.67, data_influence=21.85, cross_channel=92.80

## Most Robust Channels

- snapchat: overall=67.99, prior_sens=69.85, data_influence=47.72, cross_channel=94.32
- meta: overall=66.00, prior_sens=65.43, data_influence=50.37, cross_channel=94.33
- tiktok: overall=59.66, prior_sens=57.38, data_influence=45.25, cross_channel=92.79
