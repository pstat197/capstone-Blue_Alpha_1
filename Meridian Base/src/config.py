from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class DataConfig:
    raw_path: str

    time_col: str
    kpi_col: str
    revenue_per_kpi_col: Optional[str] = None

    # groups of features
    control_cols: List[str] = None

    # media inputs
    media_cols: List[str] = None
    media_spend_cols: List[str] = None

    # Additions
    organic_cols: List[str] = None
    reach_cols: List[str] = None
    frequency_cols: List[str] = None

@dataclass
class ModelConfig:
    # time settings
    time_granularity: str = "weekly"  # "daily" / "weekly" / "monthly"

    primary_metrics: List[str] = None  # e.g. ["roi", "mroi", "contribution"]

    # placeholder for priors
    prior_spec: Dict = None


def default_model_config() -> ModelConfig:
    return ModelConfig(
        time_granularity="weekly",
        primary_metrics=["roi", "contribution"],
        prior_spec={}
    )



DATA_CFG = DataConfig(
    raw_path="data/raw/mentor_sample.csv",
    time_col="date",
    kpi_col="subscriptions",

    control_cols=None,

    media_cols=[
        "meta_impressions",
        "google_impressions",
        "snapchat_impressions",
        "tiktok_impressions",
        "moloco_impressions",
        "liveintent_impressions",
        "roku_impressions",
        "beehiiv_impressions",
        "amazon_impressions",
    ],

    media_spend_cols=[
        "meta_spend",
        "google_spend",
        "snapchat_spend",
        "tiktok_spend",
        "moloco_spend",
        "liveintent_spend",
        "roku_spend",
        "beehiiv_spend",
        "amazon_spend",
    ],
)



