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

- Overall robustness score: **27.66** (Low)
- Weighting: `spend`
- Baseline prior: mu=0.051898, sigma=0.016722, dist=LogNormal
- Overall prior-sensitivity subscore: 23.59
- Overall data-influence subscore: 29.79
- Overall cross-channel subscore: 34.47
- Overall adstock proxy subscore: 35.14

## Most Fragile Channels

- google: overall=8.10, prior_sens=0.00, data_influence=0.00, cross_channel=42.86, adstock_proxy=33.33
- meta: overall=18.57, prior_sens=14.29, data_influence=14.29, cross_channel=14.29, adstock_proxy=100.00
- tiktok: overall=30.48, prior_sens=28.57, data_influence=28.57, cross_channel=28.57, adstock_proxy=66.67

## Most Robust Channels

- moloco: overall=100.00, prior_sens=100.00, data_influence=100.00, cross_channel=100.00, adstock_proxy=100.00
- amazon: overall=77.50, prior_sens=85.71, data_influence=71.43, cross_channel=71.43, adstock_proxy=50.00
- beehiiv: overall=70.71, prior_sens=71.43, data_influence=57.14, cross_channel=85.71, adstock_proxy=100.00
