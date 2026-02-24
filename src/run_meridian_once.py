# src/run_meridian_once.py
import argparse
from html import parser
import json
import gc
import warnings

import pandas as pd
import tensorflow as tf

import faulthandler

from meridian.data import data_frame_input_data_builder
from meridian.model import model

from src.utils import build_model_spec, extract_roi_mean

faulthandler.enable()
warnings.filterwarnings("ignore")
tf.get_logger().setLevel("ERROR")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--channels_json", required=True)
    parser.add_argument("--target_channel", required=True)
    parser.add_argument("--mu", type=float, required=True)
    parser.add_argument("--sigma", type=float, required=True)
    parser.add_argument("--dist", type=str, required=True)
    parser.add_argument("--out_csv", required=True)

    # sampling params
    parser.add_argument("--n_chains", type=int, default=1)
    parser.add_argument("--n_adapt", type=int, default=100)
    parser.add_argument("--n_burnin", type=int, default=50)
    parser.add_argument("--n_keep", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)

    parser.add_argument("--baseline_mu", type=float, required=True)
    parser.add_argument("--baseline_sigma", type=float, required=True)
    parser.add_argument("--baseline_dist", type=str, required=True)

    args = parser.parse_args()
    channels = json.loads(args.channels_json)

    # --- load data ---
    df = pd.read_csv(args.csv)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.rename(columns={"date": "time"})
    else:
        df["time"] = pd.to_datetime(df["time"])

    # --- build input_data (same as your colab builder) ---
    builder = data_frame_input_data_builder.DataFrameInputDataBuilder(
        kpi_type="non_revenue",
        default_kpi_column="subscriptions"
    )

    builder = builder.with_kpi(df)
    builder = builder.with_media(
        df,
        media_cols=[f"{c}_impressions" for c in channels],
        media_spend_cols=[f"{c}_spend" for c in channels],
        media_channels=channels
    )

    input_data = builder.build()

    # --- build spec ---
    model_spec = build_model_spec(
        channels=channels,
        target_channel=args.target_channel,
        roi_mu=args.mu,
        roi_sigma=args.sigma,
        roi_dist=args.dist
    )

    # --- fit ---
    mmm = model.Meridian(input_data=input_data, model_spec=model_spec)

    mmm.sample_posterior(
        n_chains=args.n_chains,
        n_adapt=args.n_adapt,
        n_burnin=args.n_burnin,
        n_keep=args.n_keep,
        seed=args.seed
    )

    roi_df = extract_roi_mean(mmm, channels)
    roi_df["target_channel"] = args.target_channel
    roi_df["roi_prior_mu"] = args.mu
    roi_df["roi_prior_sigma"] = args.sigma
    roi_df["roi_prior_dist"] = args.dist

    is_baseline = (
        round(args.mu, 6) == round(args.baseline_mu, 6)
        and round(args.sigma, 6) == round(args.baseline_sigma, 6)
        and args.dist == args.baseline_dist
    )

    roi_df["is_baseline"] = is_baseline

    roi_df.to_csv(args.out_csv, index=False)

    # cleanup inside subprocess
    tf.keras.backend.clear_session()
    gc.collect()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise
