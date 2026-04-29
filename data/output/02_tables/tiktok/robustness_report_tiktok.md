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

- Overall robustness score: **63.06** (High)
- Weighting: `spend`
- Baseline prior: mu=0.010460, sigma=0.010460, dist=LogNormal
- Overall prior-sensitivity subscore: 52.39
- Overall data-influence subscore: 78.03
- Overall cross-channel subscore: 67.85
- Overall adstock proxy subscore: 65.64

## Most Fragile Channels

- tiktok: overall=0.00, prior_sens=0.00, data_influence=0.00, cross_channel=0.00, adstock_proxy=0.00
- liveintent: overall=29.29, prior_sens=14.29, data_influence=42.86, cross_channel=57.14, adstock_proxy=14.29
- beehiiv: overall=40.00, prior_sens=42.86, data_influence=14.29, cross_channel=85.71, adstock_proxy=28.57

## Most Robust Channels

- google: overall=80.00, prior_sens=71.43, data_influence=100.00, cross_channel=71.43, adstock_proxy=71.43
- meta: overall=77.86, prior_sens=85.71, data_influence=85.71, cross_channel=28.57, adstock_proxy=100.00
- amazon: overall=62.86, prior_sens=100.00, data_influence=28.57, cross_channel=14.29, adstock_proxy=42.86
