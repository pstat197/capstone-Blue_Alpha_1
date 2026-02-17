from pathlib import Path
import pandas as pd

PATH = "/Users/jimmywu/Desktop/Meridian Base/data/raw/monthly_mocha.csv"

df = pd.read_csv(PATH)

print("\n=== Shape ===")
print(df.shape)

print("\n=== Columns ===")
print(list(df.columns))

print("\n=== Head ===")
print(df.head(3))

print("\n=== Missingness (top 30) ===")
na = df.isna().mean().sort_values(ascending=False)
print(na.head(30))

print("\n=== Dtypes ===")
print(df.dtypes)

# Determine the likely time column
time_candidates = [c for c in df.columns if any(k in c.lower() for k in ["date", "week", "month", "time"])]
print("\n=== Time-like column candidates ===")
print(time_candidates)

num_cols = df.select_dtypes(include="number").columns
print("\n=== Numeric summary (first 20 numeric cols) ===")
print(df[list(num_cols[:20])].describe().T[["mean", "std", "min", "max"]])
