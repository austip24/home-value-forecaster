"""Per-metro baselines and statistical models via statsforecast.

Models are fit on log ZHVI so drift and errors are proportional, then mapped back to
levels. ZHVI here is already seasonally adjusted, so ETS/ARIMA are non-seasonal;
seasonal naive is kept only because the baseline ladder requires it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import polars as pl
from statsforecast import StatsForecast
from statsforecast.models import AutoARIMA, AutoETS, Naive, RandomWalkWithDrift, SeasonalNaive

FORECAST_COLUMNS = [
    "region_id",
    "origin_date",
    "target_date",
    "horizon",
    "model",
    "value",
    "lower",
    "upper",
]

# Our model name -> statsforecast model factory (alias must equal our name).
STAT_MODELS: dict[str, Callable[[], Any]] = {
    "naive": lambda: Naive(alias="naive"),
    "seasonal_naive": lambda: SeasonalNaive(season_length=12, alias="seasonal_naive"),
    "rw_drift": lambda: RandomWalkWithDrift(alias="rw_drift"),
    "auto_ets": lambda: AutoETS(season_length=1, alias="auto_ets"),
    "auto_arima": lambda: AutoARIMA(season_length=1, alias="auto_arima"),
}

BASELINES = ("naive", "seasonal_naive", "rw_drift")
STATISTICAL = ("auto_ets", "auto_arima")


def forecast_stats(
    history: pl.DataFrame,
    origin: date,
    horizons: Sequence[int],
    models: Sequence[str],
    level: int,
    n_jobs: int = -1,
) -> pl.DataFrame:
    """Fit each model per region on `history` (region_id, date, value) ending at `origin`."""
    if not models or history.is_empty():
        return pl.DataFrame(schema=_schema())
    df = pd.DataFrame(
        {
            "unique_id": history.get_column("region_id").to_numpy(),
            "ds": pd.to_datetime(history.get_column("date").to_numpy()),
            "y": np.log(history.get_column("value").to_numpy()),
        }
    )
    sf = StatsForecast(models=[STAT_MODELS[m]() for m in models], freq="ME", n_jobs=n_jobs)
    out = pl.from_pandas(sf.forecast(df=df, h=max(horizons), level=[level]))

    frames = []
    for m in models:
        frames.append(
            out.select(
                pl.col("unique_id").cast(pl.Int64).alias("region_id"),
                pl.col("ds").cast(pl.Date).dt.month_end().alias("target_date"),
                pl.lit(m).alias("model"),
                pl.col(m).exp().alias("value"),
                pl.col(f"{m}-lo-{level}").exp().alias("lower"),
                pl.col(f"{m}-hi-{level}").exp().alias("upper"),
            )
        )
    return _with_horizon(pl.concat(frames), origin, horizons)


def _with_horizon(df: pl.DataFrame, origin: date, horizons: Sequence[int]) -> pl.DataFrame:
    months = (pl.col("target_date").dt.year() - origin.year) * 12 + (
        pl.col("target_date").dt.month() - origin.month
    )
    return (
        df.with_columns(pl.lit(origin).alias("origin_date"), months.cast(pl.Int64).alias("horizon"))
        .filter(pl.col("horizon").is_in(list(horizons)))
        .select(FORECAST_COLUMNS)
    )


def _schema() -> dict[str, pl.DataType]:
    return {
        "region_id": pl.Int64(),
        "origin_date": pl.Date(),
        "target_date": pl.Date(),
        "horizon": pl.Int64(),
        "model": pl.Utf8(),
        "value": pl.Float64(),
        "lower": pl.Float64(),
        "upper": pl.Float64(),
    }


def empty_forecasts() -> pl.DataFrame:
    return pl.DataFrame(schema=_schema())
