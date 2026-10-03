"""Backtest error metrics. Pure functions.

predictions: region_id, origin_date, target_date, horizon, model, value,
             y_origin (ZHVI at origin), scale (MASE denominator), actual
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import polars as pl

from forecaster.segments import NATIONAL_TIER, SERIES_TIER

METRICS = ("mase", "mape", "directional_accuracy")


def naive_scale(history: pl.DataFrame, origin: date) -> pl.DataFrame:
    """MASE denominator: in-sample mean absolute one-step naive error up to `origin`."""
    return (
        history.filter(pl.col("date") <= origin)
        .sort("region_id", "date")
        .group_by("region_id")
        .agg(pl.col("value").diff().abs().mean().alias("scale"))
        .with_columns(pl.lit(origin).alias("origin_date"))
    )


def row_errors(predictions: pl.DataFrame) -> pl.DataFrame:
    """Per-forecast error terms, for rows whose actual is known."""
    err = pl.col("actual") - pl.col("value")
    return predictions.drop_nulls("actual").with_columns(
        (err.abs() / pl.col("scale")).alias("scaled_abs_error"),
        (err.abs() / pl.col("actual").abs()).alias("ape"),
        (
            (pl.col("value") - pl.col("y_origin")).sign()
            == (pl.col("actual") - pl.col("y_origin")).sign()
        )
        .cast(pl.Float64)
        .alias("direction_hit"),
    )


def _aggregate(errors: pl.DataFrame, segment: str) -> pl.DataFrame:
    return (
        errors.group_by("model", "horizon")
        .agg(
            pl.col("scaled_abs_error").mean().alias("mase"),
            (pl.col("ape").mean() * 100).alias("mape"),
            pl.col("direction_hit").mean().alias("directional_accuracy"),
            pl.len().alias("n"),
        )
        .unpivot(index=["model", "horizon", "n"], on=list(METRICS), variable_name="metric")
        .with_columns(pl.lit(segment).alias("segment"))
    )


def summarize(
    predictions: pl.DataFrame,
    tiers: pl.DataFrame,
    showcase: Mapping[int, str],
    benchmark_model: str = "zhvf",
) -> pl.DataFrame:
    """`model, horizon, metric, value, segment, n` across all reporting segments.

    Segments: `all` (metros only), `national`, `size:<tier>`, `region:<RegionID>`, and
    `benchmark_matched` (only forecasts where the benchmark also has one, so models are
    compared head to head with ZHVF on identical rows).
    """
    errors = row_errors(predictions).join(tiers, on="region_id", how="left")
    metros = errors.filter(pl.col("size_tier") != NATIONAL_TIER)
    parts = [_aggregate(metros, "all")]
    for tier in errors.get_column("size_tier").drop_nulls().unique().sort().to_list():
        if tier == SERIES_TIER:
            continue  # FRED series have no size tiers; `all` already covers them.
        name = NATIONAL_TIER if tier == NATIONAL_TIER else f"size:{tier}"
        parts.append(_aggregate(errors.filter(pl.col("size_tier") == tier), name))
    for region_id in showcase:
        subset = errors.filter(pl.col("region_id") == region_id)
        if subset.height:
            parts.append(_aggregate(subset, f"region:{region_id}"))

    keys = ["region_id", "origin_date", "horizon"]
    bench = metros.filter(pl.col("model") == benchmark_model).select(keys).unique()
    if bench.height:
        parts.append(_aggregate(metros.join(bench, on=keys, how="semi"), "benchmark_matched"))

    return (
        pl.concat(parts)
        .select("model", "horizon", "metric", "value", "segment", "n")
        .sort("segment", "metric", "horizon", "model")
    )
