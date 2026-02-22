import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# Read the CSV (same folder as this script)
df = pd.read_csv("prior_sensitivity_results_all_channels.csv")

# Create a folder to store figures
out_dir = Path("figures")
out_dir.mkdir(exist_ok=True)

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

print("Done! Saved 3 plots in the figures/ folder.")

