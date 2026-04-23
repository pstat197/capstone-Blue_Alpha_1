# Robustness Score Report (google)

## Scope

- Primary scope is prior sensitivity robustness for ROI/contribution outputs under prior perturbations.
- Subscores include prior sensitivity, data influence, cross-channel coupling, and an adstock proxy stability score.

## Formula Blocks

- Sensitivity elasticity: `(Delta output / |baseline output|) / (Delta prior / |baseline prior|)`
- Data influence fragility increases when diffuse-prior runs still shift outputs strongly, flagged prior-posterior-shift rates are high, or prior-posterior distance is small.
- Cross-channel fragility increases with mean absolute correlation and spillover ratio across channels.
- Adstock proxy fragility increases with sign-flip rate, CI instability, and posterior dispersion (proxy only in current experiment).

## Overall Model Score

- Overall robustness score: **34.47** (Medium)
- Weighting: `spend`
- Baseline prior: mu=0.500000, sigma=0.500000, dist=LogNormal
- Overall prior-sensitivity subscore: 31.97
- Overall data-influence subscore: 38.09
- Overall cross-channel subscore: 35.87
- Overall adstock proxy subscore: 33.55

## Most Fragile Channels

- google: overall=0.00, prior_sens=0.00, data_influence=0.00, cross_channel=0.00, adstock_proxy=0.00
- beehiiv: overall=23.57, prior_sens=28.57, data_influence=14.29, cross_channel=28.57, adstock_proxy=14.29
- liveintent: overall=23.57, prior_sens=14.29, data_influence=42.86, cross_channel=14.29, adstock_proxy=28.57

## Most Robust Channels

- snapchat: overall=92.14, prior_sens=85.71, data_influence=100.00, cross_channel=100.00, adstock_proxy=85.71
- moloco: overall=83.57, prior_sens=100.00, data_influence=57.14, cross_channel=85.71, adstock_proxy=71.43
- tiktok: overall=67.86, prior_sens=57.14, data_influence=85.71, cross_channel=71.43, adstock_proxy=57.14
