"""Reshape Zillow's wide CSVs (one column per month) into long frames. Pure functions."""

from __future__ import annotations

import re

import polars as pl

_DATE_COL = re.compile(r"^\d{4}-\d{2}-\d{2}$")

LONG_COLUMNS = ["region_id", "region_name", "state", "date", "value"]


def date_columns(wide: pl.DataFrame) -> list[str]:
    return [c for c in wide.columns if _DATE_COL.match(c)]


def wide_to_long(wide: pl.DataFrame) -> pl.DataFrame:
    """Wide Zillow frame -> `region_id, region_name, state, date, value`, nulls dropped.

    Dates are normalised to month-end so every source joins on the same key.
    """
    dates = date_columns(wide)
    return (
        wide.select(
            pl.col("RegionID").cast(pl.Int64).alias("region_id"),
            pl.col("RegionName").cast(pl.Utf8).alias("region_name"),
            pl.col("StateName").cast(pl.Utf8).alias("state"),
            *[pl.col(d).cast(pl.Float64, strict=False) for d in dates],
        )
        .unpivot(index=["region_id", "region_name", "state"], variable_name="date")
        .drop_nulls("value")
        .with_columns(pl.col("date").str.to_date("%Y-%m-%d").dt.month_end())
        .sort("region_id", "date")
        .select(LONG_COLUMNS)
    )


def regions_from_wide(wide: pl.DataFrame) -> pl.DataFrame:
    """Region dimension table: `region_id, region_name, state, region_type, size_rank`."""
    return wide.select(
        pl.col("RegionID").cast(pl.Int64).alias("region_id"),
        pl.col("RegionName").cast(pl.Utf8).alias("region_name"),
        pl.col("StateName").cast(pl.Utf8).alias("state"),
        pl.col("RegionType").cast(pl.Utf8).alias("region_type"),
        pl.col("SizeRank").cast(pl.Int64).alias("size_rank"),
    ).sort("size_rank")


def zhvf_to_long(wide: pl.DataFrame) -> pl.DataFrame:
    """ZHVF growth file -> `region_id, origin_date, target_date, horizon, growth_pct`.

    The file has a `BaseDate` (the last ZHVI month) and one column per target month
    holding cumulative percent growth from the base date.
    """
    dates = date_columns(wide)
    long = (
        wide.select(
            pl.col("RegionID").cast(pl.Int64).alias("region_id"),
            pl.col("BaseDate").str.to_date("%Y-%m-%d").dt.month_end().alias("origin_date"),
            *[pl.col(d).cast(pl.Float64, strict=False) for d in dates],
        )
        .unpivot(index=["region_id", "origin_date"], variable_name="target_date")
        .rename({"value": "growth_pct"})
        .drop_nulls("growth_pct")
        .with_columns(pl.col("target_date").str.to_date("%Y-%m-%d").dt.month_end())
    )
    return long.with_columns(
        (
            (pl.col("target_date").dt.year() - pl.col("origin_date").dt.year()) * 12
            + pl.col("target_date").dt.month()
            - pl.col("origin_date").dt.month()
        )
        .cast(pl.Int64)
        .alias("horizon")
    ).select("region_id", "origin_date", "target_date", "horizon", "growth_pct")


def fred_to_monthly(raw: pl.DataFrame, metric: str) -> pl.DataFrame:
    """FRED `date, value` (daily/weekly/monthly) -> monthly mean at month-end."""
    return (
        raw.select(
            pl.col("date").cast(pl.Utf8).str.to_date("%Y-%m-%d").dt.month_end(),
            pl.col("value").cast(pl.Float64, strict=False),
        )
        .drop_nulls("value")
        .group_by("date")
        .agg(pl.col("value").mean())
        .with_columns(pl.lit(metric).alias("metric"))
        .sort("date")
        .select("date", "metric", "value")
    )


def fred_family_to_long(raw: pl.DataFrame) -> pl.DataFrame:
    """FRED family snapshot (`series_id, title, date, value`) -> monthly means at
    month-end, one row per series and month."""
    return (
        raw.select(
            "series_id",
            "title",
            pl.col("date").cast(pl.Utf8).str.to_date("%Y-%m-%d").dt.month_end(),
            pl.col("value").cast(pl.Float64, strict=False),
        )
        .drop_nulls("value")
        .group_by("series_id", "title", "date")
        .agg(pl.col("value").mean())
        .sort("series_id", "date")
    )
