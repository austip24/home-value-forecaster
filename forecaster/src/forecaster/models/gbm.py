"""Global LightGBM model trained across all metros, one model per horizon (direct).

Target: log growth from origin t to t + h. Features: the lag-aware matrix from
`transform.features`, so every input in the row for t is knowable at t. Training uses
only rows whose target month t + h is on or before the origin.

The direct strategy (rather than recursive) means market and macro features never need
to be forecast themselves, which keeps lookahead out by construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import lightgbm as lgb
import polars as pl

from forecaster.models.statistical import FORECAST_COLUMNS, empty_forecasts
from forecaster.transform.features import feature_columns, make_targets
from forecaster.transform.history import add_months

MODEL_NAME = "lightgbm"

NUM_BOOST_ROUND = 400

DEFAULT_PARAMS: dict[str, Any] = {
    "objective": "l2",
    "learning_rate": 0.03,
    "num_leaves": 31,
    "min_data_in_leaf": 200,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "feature_fraction": 0.8,
    "lambda_l2": 1.0,
    "seed": 42,
    "deterministic": True,
    "verbose": -1,
}


def training_frame(
    features: pl.DataFrame, zhvi: pl.DataFrame, origin: date, horizon: int
) -> pl.DataFrame:
    """Rows (region, t) with t + horizon <= origin, joined to their realised target."""
    cutoff = add_months(pl.lit(origin), -horizon)
    targets = make_targets(zhvi.filter(pl.col("date") <= origin), horizon)
    return (
        features.filter(pl.col("date") <= cutoff)
        .join(targets, on=["region_id", "date"], how="inner")
        .drop_nulls("target")
    )


def forecast_gbm(
    features: pl.DataFrame,
    zhvi: pl.DataFrame,
    origin: date,
    horizons: Sequence[int],
    params: dict[str, Any] | None = None,
    n_jobs: int = -1,
) -> pl.DataFrame:
    """Fit one model per horizon and predict for every region present at `origin`."""
    cols = feature_columns(features)
    predict_rows = features.filter(pl.col("date") == origin)
    if predict_rows.is_empty():
        return empty_forecasts()

    frames = []
    for h in horizons:
        train = training_frame(features, zhvi, origin, h)
        dataset = lgb.Dataset(
            train.select(cols).to_numpy(),
            label=train.get_column("target").to_numpy(),
            feature_name=cols,
        )
        booster = lgb.train(
            {**DEFAULT_PARAMS, **(params or {}), "num_threads": max(n_jobs, 0)},
            dataset,
            num_boost_round=NUM_BOOST_ROUND,
        )
        growth = booster.predict(predict_rows.select(cols).to_numpy())
        frames.append(
            predict_rows.select(
                "region_id",
                pl.lit(origin).alias("origin_date"),
                add_months(pl.lit(origin), h).alias("target_date"),
                pl.lit(h, dtype=pl.Int64).alias("horizon"),
                pl.lit(MODEL_NAME).alias("model"),
                (pl.col("y") + pl.Series(growth)).exp().alias("value"),
                pl.lit(None, dtype=pl.Float64).alias("lower"),
                pl.lit(None, dtype=pl.Float64).alias("upper"),
            )
        )
    return pl.concat(frames).select(FORECAST_COLUMNS)
