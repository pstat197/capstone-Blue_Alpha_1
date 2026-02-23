# src/run_meridian_once.py
import argparse
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

    # multi-prior overrides
    parser.add_argument("--roi_prior_overrides_json", default=None)

    parser.add_argument("--target_channel", default=None)
    parser.add_argument("--mu", type=float, default=None)
    parser.add_argument("--sigma", type=float, default=None)
    parser.add_argument("--dist", type=str, default=None)

    parser.add_argument("--out_csv", required=True)

    parser.add_argument("--n_chains", type=int, default=1)
    parser.add_argument("--n_adapt", type=int, default=100)
    parser.add_argument("--n_burnin", type=int, default=50)
    parser.add_argument("--n_keep", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)

    args = parser.parse_args()
    channels = json.loads(args.channels_json)

    # determine mode
    multiprior = args.roi_prior_overrides_json is not None

    if not multiprior:
        if args.target_channel is None or args.mu is None or args.sigma is None or args.dist is None:
            raise ValueError(
                "Single-target mode requires --target_channel, --mu, --sigma, --dist "
                "OR provide --roi_prior_overrides_json for multi-prior mode."
            )

    # load data
    df = pd.read_csv(args.csv)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.rename(columns={"date": "time"})
    else:
        df["time"] = pd.to_datetime(df["time"])

    # build input_data
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

    # build spec
    if multiprior:
        overrides = json.loads(args.roi_prior_overrides_json)
        model_spec = build_model_spec(
            channels=channels,
            roi_prior_overrides=overrides
        )

        targets = sorted(list(overrides.keys()))
        targets_str = ",".join(targets)

        first = overrides[targets[0]]
        shared_mu = first.get("mu", None)
        shared_sigma = first.get("sigma", None)
        shared_dist = first.get("dist", None)

        prior_key = json.dumps(overrides, sort_keys=True)

    else:
        model_spec = build_model_spec(
            channels=channels,
            target_channel=args.target_channel,
            roi_mu=args.mu,
            roi_sigma=args.sigma,
            roi_dist=args.dist
        )
        targets_str = args.target_channel
        shared_mu = args.mu
        shared_sigma = args.sigma
        shared_dist = args.dist
        prior_key = None

    # fit
    mmm = model.Meridian(input_data=input_data, model_spec=model_spec)

    mmm.sample_posterior(
        n_chains=args.n_chains,
        n_adapt=args.n_adapt,
        n_burnin=args.n_burnin,
        n_keep=args.n_keep,
        seed=args.seed
    )

    roi_df = extract_roi_mean(mmm, channels)

    # write output
    roi_df["target_channel"] = targets_str
    roi_df["roi_prior_mu"] = shared_mu
    roi_df["roi_prior_sigma"] = shared_sigma
    roi_df["roi_prior_dist"] = shared_dist

    if multiprior:
        roi_df["targets"] = targets_str
        roi_df["prior_key"] = prior_key
        roi_df["roi_prior_overrides_json"] = prior_key

    roi_df.to_csv(args.out_csv, index=False)

    # cleanup inside subprocess
    tf.keras.backend.clear_session()
    gc.collect()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        raise