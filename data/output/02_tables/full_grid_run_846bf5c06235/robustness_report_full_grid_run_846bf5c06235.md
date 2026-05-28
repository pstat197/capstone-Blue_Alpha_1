# Robustness Score Report (amazon,google,meta,snapchat,tiktok)

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

- Overall robustness score: **55.12** (Medium)
- Weighting: `spend`
- Baseline prior: mu=1.000000, sigma=1.000000, dist=LogNormal
- Overall sensitivity-elasticity subscore (60%): 53.11
- Overall data-influence subscore (25%): 37.99
- Overall cross-channel subscore (15%): 91.72

## Most Fragile Channels

- google: overall=50.46, prior_sens=46.02, data_influence=36.69, cross_channel=91.18
- tiktok: overall=50.60, prior_sens=49.37, data_influence=28.09, cross_channel=93.05
- meta: overall=54.75, prior_sens=57.25, data_influence=26.33, cross_channel=92.14

## Most Robust Channels

- snapchat: overall=68.05, prior_sens=70.59, data_influence=47.38, cross_channel=92.38
- amazon: overall=58.59, prior_sens=65.52, data_influence=21.92, cross_channel=91.99
- meta: overall=54.75, prior_sens=57.25, data_influence=26.33, cross_channel=92.14
