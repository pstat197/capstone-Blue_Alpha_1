# Robustness Score Report (amazon,beehiiv,google,liveintent,meta,moloco,snapchat,tiktok)

## Scope

- Primary scope is prior sensitivity robustness for ROI/contribution outputs under prior perturbations.
- Subscores include prior sensitivity, data influence, cross-channel coupling, and an adstock proxy stability score.

## Formula Blocks

- Sensitivity elasticity: `(Delta output / |baseline output|) / (Delta prior / |baseline prior|)`
- Data influence fragility increases when diffuse-prior runs still shift outputs strongly, flagged prior-posterior-shift rates are high, or prior-posterior distance is small.
- Cross-channel fragility increases with mean absolute correlation and spillover ratio across channels.
- Adstock proxy fragility increases with sign-flip rate, CI instability, and posterior dispersion (proxy only in current experiment).

## Overall Model Score

- Overall robustness score: **60.95** (High)
- Weighting: `spend`
- Baseline prior: mu=1.000000, sigma=1.000000, dist=LogNormal
- Overall prior-sensitivity subscore: 51.21
- Overall data-influence subscore: 83.35
- Overall cross-channel subscore: 40.84
- Overall adstock proxy subscore: 84.37

## Most Fragile Channels

- amazon: overall=16.43, prior_sens=14.29, data_influence=0.00, cross_channel=57.14, adstock_proxy=14.29
- meta: overall=35.71, prior_sens=0.00, data_influence=57.14, cross_channel=100.00, adstock_proxy=71.43
- moloco: overall=36.43, prior_sens=42.86, data_influence=42.86, cross_channel=0.00, adstock_proxy=42.86

## Most Robust Channels

- tiktok: overall=84.29, prior_sens=85.71, data_influence=85.71, cross_channel=85.71, adstock_proxy=57.14
- snapchat: overall=77.86, prior_sens=100.00, data_influence=71.43, cross_channel=14.29, adstock_proxy=85.71
- google: overall=55.71, prior_sens=28.57, data_influence=100.00, cross_channel=42.86, adstock_proxy=100.00
