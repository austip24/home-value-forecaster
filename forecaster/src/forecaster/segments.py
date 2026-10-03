"""Reporting segments: metro size tiers, the national series, and showcase metros."""

from __future__ import annotations

import polars as pl

NATIONAL_TIER = "national"
# FRED macro series are one tier: national, and not comparable by size.
SERIES_TIER = "series"


def size_tiers(regions: pl.DataFrame) -> pl.DataFrame:
    """`region_id, size_tier` from Zillow's SizeRank (0 is the national series)."""
    rank = pl.col("size_rank")
    tier = (
        pl.when(pl.col("region_type") == "series")
        .then(pl.lit(SERIES_TIER))
        .when(pl.col("region_type") == "country")
        .then(pl.lit(NATIONAL_TIER))
        .when(rank <= 50)
        .then(pl.lit("1-50"))
        .when(rank <= 200)
        .then(pl.lit("51-200"))
        .otherwise(pl.lit("201+"))
    )
    return regions.select("region_id", tier.alias("size_tier"))
