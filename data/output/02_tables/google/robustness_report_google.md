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

- Overall robustness score: **31.36** (Low)
- Weighting: `spend`
- Baseline prior: mu=0.001780, sigma=0.001780, dist=LogNormal
- Overall prior-sensitivity subscore: 31.42
- Overall data-influence subscore: 32.30
- Overall cross-channel subscore: 29.07
- Overall adstock proxy subscore: 31.95

## Most Fragile Channels

- google: overall=0.00, prior_sens=0.00, data_influence=0.00, cross_channel=0.00, adstock_proxy=0.00
- liveintent: overall=18.57, prior_sens=14.29, data_influence=28.57, cross_channel=14.29, adstock_proxy=14.29
- beehiiv: overall=32.86, prior_sens=28.57, data_influence=14.29, cross_channel=85.71, adstock_proxy=28.57

## Most Robust Channels

- meta: overall=78.57, prior_sens=57.14, data_influence=100.00, cross_channel=100.00, adstock_proxy=100.00
- snapchat: overall=78.57, prior_sens=85.71, data_influence=71.43, cross_channel=71.43, adstock_proxy=71.43
- tiktok: overall=74.29, prior_sens=71.43, data_influence=85.71, cross_channel=57.14, adstock_proxy=85.71
