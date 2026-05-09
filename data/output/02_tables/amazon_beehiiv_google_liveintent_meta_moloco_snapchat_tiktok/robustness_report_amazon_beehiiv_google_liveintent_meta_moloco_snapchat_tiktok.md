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

- Overall robustness score: **46.61** (Medium)
- Weighting: `spend`
- Baseline prior: mu=1.000000, sigma=1.000000, dist=LogNormal
- Overall prior-sensitivity subscore: 30.72
- Overall data-influence subscore: 80.07
- Overall cross-channel subscore: 20.93
- Overall adstock proxy subscore: 81.76

## Most Fragile Channels

- beehiiv: overall=15.71, prior_sens=14.29, data_influence=14.29, cross_channel=28.57, adstock_proxy=0.00
- amazon: overall=25.71, prior_sens=28.57, data_influence=0.00, cross_channel=71.43, adstock_proxy=14.29
- google: overall=35.00, prior_sens=0.00, data_influence=100.00, cross_channel=0.00, adstock_proxy=100.00

## Most Robust Channels

- meta: overall=71.43, prior_sens=57.14, data_influence=85.71, cross_channel=85.71, adstock_proxy=85.71
- liveintent: overall=66.43, prior_sens=100.00, data_influence=28.57, cross_channel=42.86, adstock_proxy=28.57
- moloco: overall=66.43, prior_sens=85.71, data_influence=42.86, cross_channel=57.14, adstock_proxy=42.86
