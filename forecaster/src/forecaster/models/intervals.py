"""Split-conformal prediction intervals from out-of-sample backtest errors."""

from __future__ import annotations

import polars as pl

from forecaster.models.statistical import FORECAST_COLUMNS


def conformal_quantiles(errors: pl.DataFrame, level: int) -> pl.DataFrame:
    """Per (model, horizon, size_tier) quantiles of log errors log(actual / forecast).

    errors: model, horizon, size_tier, log_error
    """
    alpha = (100 - level) / 100
    return errors.group_by("model", "horizon", "size_tier").agg(
        pl.col("log_error").quantile(alpha / 2, interpolation="linear").alias("q_lo"),
        pl.col("log_error").quantile(1 - alpha / 2, interpolation="linear").alias("q_hi"),
        pl.len().alias("n"),
    )


def apply_conformal(
    forecasts: pl.DataFrame, quantiles: pl.DataFrame, tiers: pl.DataFrame
) -> pl.DataFrame:
    """Fill lower/upper for forecasts that lack them, using matching backtest quantiles.

    tiers: region_id, size_tier
    """
    joined = forecasts.join(tiers, on="region_id", how="left").join(
        quantiles.select("model", "horizon", "size_tier", "q_lo", "q_hi"),
        on=["model", "horizon", "size_tier"],
        how="left",
    )
    return joined.with_columns(
        pl.coalesce("lower", pl.col("value") * pl.col("q_lo").exp()).alias("lower"),
        pl.coalesce("upper", pl.col("value") * pl.col("q_hi").exp()).alias("upper"),
    ).select(FORECAST_COLUMNS)
