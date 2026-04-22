# Robustness Score Report (google,meta,tiktok)

## Scope

- Primary scope is prior sensitivity robustness for ROI/contribution outputs under prior perturbations.
- Subscores include prior sensitivity, data influence, cross-channel coupling, and an adstock proxy stability score.

## Formula Blocks

- Sensitivity elasticity: `(Delta output / |baseline output|) / (Delta prior / |baseline prior|)`
- Data influence fragility increases when diffuse-prior runs still shift outputs strongly, flagged prior-posterior-shift rates are high, or prior-posterior distance is small.
- Cross-channel fragility increases with mean absolute correlation and spillover ratio across channels.
- Adstock proxy fragility increases with sign-flip rate, CI instability, and posterior dispersion (proxy only in current experiment).

## Overall Model Score

- Overall robustness score: **44.70** (Medium)
- Weighting: `spend`
- Baseline prior: mu=0.275949, sigma=0.258361, dist=LogNormal
- Overall prior-sensitivity subscore: 39.63
- Overall data-influence subscore: 55.56
- Overall cross-channel subscore: 42.85
- Overall adstock proxy subscore: 35.82

## Most Fragile Channels

- tiktok: overall=8.57, prior_sens=0.00, data_influence=28.57, cross_channel=0.00, adstock_proxy=0.00
- meta: overall=15.00, prior_sens=14.29, data_influence=14.29, cross_channel=14.29, adstock_proxy=28.57
- beehiiv: overall=30.00, prior_sens=42.86, data_influence=0.00, cross_channel=42.86, adstock_proxy=42.86

## Most Robust Channels

- moloco: overall=95.71, prior_sens=100.00, data_influence=85.71, cross_channel=100.00, adstock_proxy=100.00
- snapchat: overall=82.86, prior_sens=71.43, data_influence=100.00, cross_channel=85.71, adstock_proxy=85.71
- amazon: overall=74.29, prior_sens=85.71, data_influence=57.14, cross_channel=71.43, adstock_proxy=71.43
