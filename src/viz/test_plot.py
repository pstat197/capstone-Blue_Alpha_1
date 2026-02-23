import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# Paths
ROOT = Path(__file__).resolve().parents[2]

csv_path = ROOT / "data" / "output" / "prior_sensitivity_results_all_channels.csv"
out_dir = ROOT / "docs" / "figures"
out_dir.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(csv_path)

# 1) Histogram of Estimated ROI
plt.figure()
plt.hist(df["estimated_roi"], bins=20)
plt.title("Distribution of Estimated ROI")
plt.xlabel("Estimated ROI")
plt.ylabel("Frequency")
plt.tight_layout()
plt.savefig(out_dir / "roi_histogram.png", dpi=300, bbox_inches="tight")
plt.close()

# 2) Scatter: Prior Mean vs Estimated ROI
plt.figure()
plt.scatter(df["roi_prior_mu"], df["estimated_roi"])
plt.title("Prior Mean vs Estimated ROI")
plt.xlabel("ROI Prior Mean (mu)")
plt.ylabel("Estimated ROI")
plt.tight_layout()
plt.savefig(out_dir / "prior_mean_vs_roi.png", dpi=300, bbox_inches="tight")
plt.close()

# 3) Scatter: Prior Sigma vs Estimated ROI
plt.figure()
plt.scatter(df["roi_prior_sigma"], df["estimated_roi"])
plt.title("Prior Sigma vs Estimated ROI")
plt.xlabel("ROI Prior Sigma")
plt.ylabel("Estimated ROI")
plt.tight_layout()
plt.savefig(out_dir / "prior_sigma_vs_roi.png", dpi=300, bbox_inches="tight")
plt.close()

print(f"Done! Saved 3 plots to: {out_dir}")