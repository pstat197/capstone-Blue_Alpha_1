import pandas as pd

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "prior_sigma": "roi_prior_sigma",
        "sigma": "roi_prior_sigma",
        "roi_sigma": "roi_prior_sigma",
        "roi_prior_sd": "roi_prior_sigma",

        "prior_mu": "roi_prior_mu",
        "mu": "roi_prior_mu",
        "roi_mu": "roi_prior_mu",

        "dist": "roi_prior_dist",
        "prior_dist": "roi_prior_dist",
        "roi_dist": "roi_prior_dist",

        "channel": "target_channel",
        "target": "target_channel",
    }

    for old, new in rename_map.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})

    for col in ["target_channel", "roi_prior_mu", "roi_prior_sigma", "roi_prior_dist"]:
        if col not in df.columns:
            df[col] = pd.NA

    return df
