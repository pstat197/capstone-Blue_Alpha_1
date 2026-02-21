# src/experiment.py
import os
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ExperimentConfig:
    project_root: str
    data_csv: str
    src_dir: str
    output_dir: str
    output_file: str
    channels: List[str]
    spend_cols: List[str]
    mu0: float
    multipliers: List[float]
    roi_mu_values: List[float]
    roi_sigma_values: List[float]
    roi_dist_values: List[str]


def compute_mu0(df: pd.DataFrame, kpi_col: str, spend_cols: List[str]) -> float:
    total_spend = df[spend_cols].sum(axis=1)
    mu0 = (df[kpi_col] / total_spend).median()
    return float(mu0)

def compute_sigma0(df: pd.DataFrame, kpi_col: str, spend_cols: List[str]) -> float:
    total_spend = df[spend_cols].sum(axis=1)
    roi = df[kpi_col] / total_spend
    sigma0 = roi.std()
    return float(sigma0)

def make_mu_grid(mu0: float, multipliers: List[float], digits: int = 6) -> List[float]:
    return [round(mu0 * m, digits) for m in multipliers]

def make_sigma_grid(sigma0: float, multipliers: List[float], digits: int = 6) -> List[float]:
    return [round(sigma0 * m, digits) for m in multipliers]


def build_experiment_config(
    channels: List[str],
    multipliers: List[float],
    kpi_col: str = "subscriptions",
    spend_suffix: str = "_spend",
    sigma_grid: list = None,
    dist_grid: list = None,
    output_file: Optional[str] = None,  
) -> ExperimentConfig:

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_csv = os.path.join(project_root, "data", "raw", "monthly_mocha.csv")
    src_dir = os.path.join(project_root, "src")
    output_dir = os.path.join(project_root, "data", "output")
    os.makedirs(output_dir, exist_ok=True)

    if output_file is None:
        output_file = "prior_sensitivity_results.csv"

    if not os.path.isabs(output_file):
        output_file = os.path.join(output_dir, output_file)

    df = pd.read_csv(data_csv)

    spend_cols = [f"{ch}{spend_suffix}" for ch in channels]

    missing = [c for c in spend_cols if c not in df.columns]
    if missing:
        raise KeyError(
            "Missing spend columns in CSV: "
            + ", ".join(missing)
            + "\nAvailable columns: "
            + ", ".join(df.columns)
        )

    mu0 = compute_mu0(df, kpi_col=kpi_col, spend_cols=spend_cols)
    roi_mu_values = make_mu_grid(mu0, multipliers)

    sigma0 = compute_sigma0(df, kpi_col=kpi_col, spend_cols=spend_cols)
    roi_sigma_values = make_sigma_grid(sigma0, multipliers) if sigma_grid is None else sigma_grid

    roi_dist_values = ["Normal", "LogNormal"] if dist_grid is None else dist_grid

    return ExperimentConfig(
        project_root=project_root,
        data_csv=data_csv,
        src_dir=src_dir,
        output_dir=output_dir,
        output_file=output_file,
        channels=channels,
        spend_cols=spend_cols,
        mu0=mu0,
        multipliers=multipliers,
        roi_mu_values=roi_mu_values,
        roi_sigma_values=roi_sigma_values,
        roi_dist_values=roi_dist_values,
    )