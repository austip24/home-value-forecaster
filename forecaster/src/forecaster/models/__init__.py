"""Baselines, statsforecast models, and the global LightGBM model."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import date

import polars as pl

from forecaster import config
from forecaster.config import HORIZONS, INTERVAL_LEVEL, MIN_HISTORY_MONTHS, forecasts_table
from forecaster.models import gbm
from forecaster.models.benchmark import zhvf_levels
from forecaster.models.intervals import apply_conformal, conformal_quantiles
from forecaster.models.statistical import (
    BASELINES,
    STAT_MODELS,
    STATISTICAL,
    empty_forecasts,
    forecast_stats,
)
from forecaster.runs import latest_run
from forecaster.segments import size_tiers
from forecaster.store import load, target_names, write_table
from forecaster.transform.features import build_features
from forecaster.transform.history import filter_min_history, published_by

log = logging.getLogger(__name__)

# In build order; each stage has to beat the previous one in the backtest.
ALL_MODELS: tuple[str, ...] = (*BASELINES, *STATISTICAL, gbm.MODEL_NAME)


def forecast_origin(
    history: pl.DataFrame,
    regions: pl.DataFrame,
    market: pl.DataFrame | None,
    macro: pl.DataFrame | None,
    lags: Mapping[str, int],
    origin: date,
    horizons: Sequence[int] = HORIZONS,
    models: Sequence[str] = ALL_MODELS,
    level: int = INTERVAL_LEVEL,
    n_jobs: int | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Forecast every eligible region from data knowable at `origin`.

    Returns (forecasts, excluded) where `excluded` lists series dropped for short or
    stale history.
    """
    n_jobs = config.N_JOBS if n_jobs is None else n_jobs
    history = history.filter(pl.col("date") <= origin)
    eligible, excluded = filter_min_history(history, MIN_HISTORY_MONTHS, origin)
    frames = [
        forecast_stats(
            eligible, origin, horizons, [m for m in models if m in STAT_MODELS], level, n_jobs
        )
    ]
    if gbm.MODEL_NAME in models:
        features = build_features(
            history,
            regions,
            published_by(market, origin, lags) if market is not None else None,
            published_by(macro, origin, lags) if macro is not None else None,
            lags,
        ).join(eligible.select("region_id").unique(), on="region_id", how="semi")
        frames.append(gbm.forecast_gbm(features, eligible, origin, horizons, n_jobs=n_jobs))
    frames = [f for f in frames if f.height]
    return (pl.concat(frames) if frames else empty_forecasts()), excluded


def backtest_log_errors(predictions: pl.DataFrame, regions: pl.DataFrame) -> pl.DataFrame:
    """log(actual / forecast) per backtest prediction, tagged with size tier."""
    return (
        predictions.drop_nulls("actual")
        .join(size_tiers(regions), on="region_id", how="left")
        .select(
            "model",
            "horizon",
            "size_tier",
            (pl.col("actual") / pl.col("value")).log().alias("log_error"),
        )
    )


def run(release: str, dataset: str = "zillow") -> None:
    ds = load(release, dataset)
    origin = ds.zhvi.get_column("date").max()
    assert isinstance(origin, date)
    log.info("forecasting %s from origin %s (release %s)", dataset, origin, release)

    forecasts, excluded = forecast_origin(ds.zhvi, ds.regions, ds.market, ds.macro, ds.lags, origin)
    if excluded.height:
        log.info("excluded %d series with short or stale history", excluded.height)

    # Only Zillow publishes a benchmark forecast; FRED series have none.
    if ds.kind == "zillow":
        if ds.zhvf is not None:
            zhvf = zhvf_levels(ds.zhvf, ds.zhvi).filter(
                (pl.col("origin_date") == origin) & pl.col("horizon").is_in(list(HORIZONS))
            )
            forecasts = pl.concat([forecasts, zhvf])
            log.info("added %d ZHVF benchmark forecasts", zhvf.height)
        else:
            log.warning("no ZHVF snapshot for %s; benchmark omitted", release)

    bt = latest_run(release, dataset)
    if bt is None:
        log.warning("no backtest run for %s; LightGBM forecasts have no intervals", release)
    else:
        quantiles = conformal_quantiles(
            backtest_log_errors(bt.predictions(), ds.regions), INTERVAL_LEVEL
        )
        forecasts = apply_conformal(forecasts, quantiles, size_tiers(ds.regions))
        log.info("conformal intervals from backtest run %s", bt.run_id)

    forecasts = forecasts.with_columns(
        target_names(ds).alias("target"), pl.lit(release).alias("release")
    ).sort("region_id", "model", "horizon")
    path = write_table(release, forecasts_table(dataset), forecasts)
    log.info("wrote %d forecasts -> %s", forecasts.height, path)
