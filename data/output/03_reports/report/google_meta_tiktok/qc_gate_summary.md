# QC Gate Summary (google_meta_tiktok)

- Generated at: 2026-04-02 15:04:29
- Targets: google, meta, tiktok
- Source run CSV: `D:\Intern\BlueAlpha\data\output\01_runs\google_meta_tiktok\prior_sensitivity_runs_multi_google_meta_tiktok.csv`
- Source tornado CSV: `D:\Intern\BlueAlpha\data\output\02_tables\google_meta_tiktok\tornado_google_meta_tiktok.csv`

## Gate Decision

- Result: **PASS**
- QC window status: PASS=4, REVIEW=0, FAIL=0 (n=4)
- PASS rate in QC window: 100.0%
- Context vs full explored scope: QC window n=4 out of total n=18; outside window status = PASS 7, REVIEW 5, FAIL 2

## Fit Sanity (QC Window)

- Mean R2: 0.8889
- Mean MAPE: 0.0519
- Mean wMAPE: 0.0511
- Max baseline negative probability: 0.0000

## Artifacts

- Run subset table: `tables/qc_gate_run_subset.csv`
- Channel sensitivity table: `tables/qc_gate_channel_sensitivity.csv`

## Sensitivity Snapshot

- Ranking metric: `delta_value_abs`
- google: max=31352603.4663, median=25981967.8953, n=4
- liveintent: max=15299903.8279, median=11924963.1110, n=4
- tiktok: max=7909035.7972, median=3732996.6537, n=4
- beehiiv: max=5021496.8629, median=2408508.0006, n=4
- snapchat: max=4464436.3712, median=1987519.6511, n=4

## Recommended Next Step

- Use this QC-passing 4-run window as the default gate for final capstone deliverables.
- Keep high-mu + LogNormal scenarios in appendix as stress tests (not decision defaults).
