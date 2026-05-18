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

- Overall robustness score: **42.37** (Low)
- Weighting: `spend`
- Baseline prior: mu=0.500000, sigma=0.500000, dist=LogNormal
- Overall prior-sensitivity subscore: 24.88
- Overall data-influence subscore: 71.02
- Overall cross-channel subscore: 31.10
- Overall adstock proxy subscore: 79.32

## Most Fragile Channels

- snapchat: overall=22.14, prior_sens=0.00, data_influence=14.29, cross_channel=100.00, adstock_proxy=57.14
- moloco: overall=41.43, prior_sens=28.57, data_influence=71.43, cross_channel=28.57, adstock_proxy=28.57
- google: overall=42.14, prior_sens=14.29, data_influence=100.00, cross_channel=0.00, adstock_proxy=100.00

## Most Robust Channels

- tiktok: overall=82.14, prior_sens=100.00, data_influence=85.71, cross_channel=14.29, adstock_proxy=85.71
- meta: overall=60.00, prior_sens=57.14, data_influence=57.14, cross_channel=71.43, adstock_proxy=71.43
- amazon: overall=59.29, prior_sens=71.43, data_influence=28.57, cross_channel=85.71, adstock_proxy=42.86
