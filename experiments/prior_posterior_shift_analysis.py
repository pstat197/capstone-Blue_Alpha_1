# ============================================================
# Prior Sensitivity + PriorPosteriorShift Full Test Script
# ============================================================

import os
import sys
import subprocess
import json
import pandas as pd
import numpy as np


# ----------------------------
# CONFIG
# ----------------------------

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_CSV = os.path.join(PROJECT_ROOT, "data", "raw", "monthly_mocha.csv")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHANNELS = [
    "meta",
    "google",
    "snapchat",
    "tiktok",
    "moloco",
    "liveintent",
    "beehiiv",
    "amazon",
]

channels_json = json.dumps(CHANNELS)

KPI_COL = "subscriptions"     # change to "revenue" if needed
SPEND_SUFFIX = "_spend"

# Prior strength multipliers (tight → weak)
MULTIPLIERS = [0.5, 1.0, 2.0, 5.0]


# ----------------------------
# LOAD DATA
# ----------------------------

df = pd.read_csv(DATA_CSV)

spend_cols = [c + SPEND_SUFFIX for c in CHANNELS]

missing = [c for c in spend_cols if c not in df.columns]
if missing:
    raise KeyError(f"Missing spend columns: {missing}")

# If using revenue instead of subscriptions:
# df["revenue"] = df["subscriptions"] * 100


# ----------------------------
# COMPUTE BASELINE mu0, sigma0
# ----------------------------

total_spend = df[spend_cols].sum(axis=1)

roi = df[KPI_COL] / total_spend

mu0 = roi.median()
sigma0 = roi.std()

print("\n============================")
print("BASELINE PRIOR STATS")
print("============================")
print("mu0:", mu0)
print("sigma0:", sigma0)


# ----------------------------
# PRIOR GRID
# ----------------------------

mu_grid = [round(mu0 * m, 6) for m in MULTIPLIERS]
sigma_grid = [round(sigma0 * m, 6) for m in MULTIPLIERS]

print("\nMu grid:", mu_grid)
print("Sigma grid:", sigma_grid)


# ----------------------------
# RUN FOR ALL CHANNELS
# ----------------------------

for target_channel in CHANNELS:

    print("\n====================================")
    print(f"Testing Target Channel: {target_channel}")
    print("====================================")

    for mu in mu_grid:
        for sigma in sigma_grid:

            print(f"Running mu={mu}, sigma={sigma}")

            tmp_out = os.path.join(
                OUTPUT_DIR,
                f"prior_test_{target_channel}_mu{mu}_sigma{sigma}.csv"
            )

            cmd = [
                sys.executable,
                "-m",
                "src.run_meridian_once",
                "--csv", DATA_CSV,
                "--channels_json", channels_json,
                "--target_channel", target_channel,
                "--mu", str(mu),
                "--sigma", str(sigma),
                "--dist", "LogNormal",
                "--out_csv", tmp_out,
                "--n_chains", "4",
                "--n_adapt", "500",
                "--n_burnin", "500",
                "--n_keep", "500",
                "--seed", "0",
            ]

            result = subprocess.run(
                cmd,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                print("ERROR:")
                print(result.stderr)
            else:
                print("✓ Completed")


print("\n====================================")
print("ALL PRIOR SENSITIVITY RUNS COMPLETE")
print("Now check PriorPosteriorShift in outputs.")
print("====================================")