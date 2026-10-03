"""Zillow Home Value Forecast (ZHVF) as a benchmark model."""

from __future__ import annotations

import polars as pl

from forecaster.models.statistical import FORECAST_COLUMNS

MODEL_NAME = "zhvf"


def zhvf_levels(zhvf: pl.DataFrame, zhvi: pl.DataFrame) -> pl.DataFrame:
    """Convert ZHVF cumulative growth (%) to levels using ZHVI at each forecast origin.

    `zhvi` should be the same vintage as `zhvf` (the same release's snapshot), so the
    base value is the one Zillow grew from.
    """
    base = zhvi.select(
        "region_id", pl.col("date").alias("origin_date"), pl.col("value").alias("base_value")
    )
    return (
        zhvf.join(base, on=["region_id", "origin_date"], how="inner")
        .with_columns(
            pl.lit(MODEL_NAME).alias("model"),
            (pl.col("base_value") * (1 + pl.col("growth_pct") / 100)).alias("value"),
            pl.lit(None, dtype=pl.Float64).alias("lower"),
            pl.lit(None, dtype=pl.Float64).alias("upper"),
        )
        .select(FORECAST_COLUMNS)
    )
