# Robustness Score Report (tiktok)

## Scope

- Primary scope is prior sensitivity robustness for ROI/contribution outputs under prior perturbations.
- Subscores include prior sensitivity, data influence, cross-channel coupling, and an adstock proxy stability score.

## Formula Blocks

- Sensitivity elasticity: `(Delta output / |baseline output|) / (Delta prior / |baseline prior|)`
- Data influence fragility increases when diffuse-prior runs still shift outputs strongly, flagged prior-posterior-shift rates are high, or prior-posterior distance is small.
- Cross-channel fragility increases with mean absolute correlation and spillover ratio across channels.
- Adstock proxy fragility increases with sign-flip rate, CI instability, and posterior dispersion (proxy only in current experiment).

## Overall Model Score

- Overall robustness score: **77.40** (High)
- Weighting: `spend`
- Baseline prior: mu=1.500000, sigma=1.500000, dist=LogNormal
- Overall prior-sensitivity subscore: 76.14
- Overall data-influence subscore: 80.63
- Overall cross-channel subscore: 75.52
- Overall adstock proxy subscore: 76.20

## Most Fragile Channels

- tiktok: overall=0.00, prior_sens=0.00, data_influence=0.00, cross_channel=0.00, adstock_proxy=0.00
- beehiiv: overall=14.29, prior_sens=14.29, data_influence=14.29, cross_channel=14.29, adstock_proxy=14.29
- amazon: overall=30.71, prior_sens=28.57, data_influence=28.57, cross_channel=42.86, adstock_proxy=28.57

## Most Robust Channels

- snapchat: overall=95.71, prior_sens=100.00, data_influence=85.71, cross_channel=100.00, adstock_proxy=100.00
- google: overall=90.00, prior_sens=85.71, data_influence=100.00, cross_channel=85.71, adstock_proxy=85.71
- liveintent: overall=61.43, prior_sens=71.43, data_influence=42.86, cross_channel=71.43, adstock_proxy=42.86
