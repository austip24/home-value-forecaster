"""Reshape wide Zillow CSVs to long format and build features without lookahead."""

from __future__ import annotations

import logging

import polars as pl

from forecaster.config import MIN_HISTORY_MONTHS
from forecaster.ingest.readers import read_fred, read_fred_family, read_zillow
from forecaster.sources import FRED_METRO_UNEMPLOYMENT, FRED_SOURCES, MARKET_SOURCES, ZHVF, ZHVI
from forecaster.store import Dataset, publication_lags, write_table
from forecaster.transform.crosswalk import match_metros
from forecaster.transform.features import build_features
from forecaster.transform.history import filter_min_history
from forecaster.transform.reshape import (
    fred_family_to_long,
    fred_to_monthly,
    regions_from_wide,
    wide_to_long,
    zhvf_to_long,
)

log = logging.getLogger(__name__)

# Metros plus the national series (used for national features and the overview).
REGION_TYPES = ("msa", "country")


def load_raw(release: str) -> Dataset:
    """Read a release's raw snapshots into long frames."""
    zhvi_wide = read_zillow(ZHVI, release)
    if zhvi_wide is None:
        raise FileNotFoundError(f"no ZHVI snapshot for release {release}; run ingest first")
    regions = regions_from_wide(zhvi_wide).filter(pl.col("region_type").is_in(REGION_TYPES))
    zhvi = wide_to_long(zhvi_wide).join(regions.select("region_id"), on="region_id", how="semi")

    market_frames = []
    for source in MARKET_SOURCES:
        wide = read_zillow(source, release)
        if wide is None:
            log.warning("no %s snapshot for %s; features will omit it", source.metric, release)
            continue
        market_frames.append(
            wide_to_long(wide).select(
                "region_id", "date", pl.lit(source.metric).alias("metric"), "value"
            )
        )

    macro_frames = []
    for fred_source in FRED_SOURCES:
        raw = read_fred(fred_source, release)
        if raw is None:
            log.warning("no FRED %s snapshot for %s", fred_source.metric, release)
            continue
        macro_frames.append(fred_to_monthly(raw, fred_source.metric))

    zhvf_wide = read_zillow(ZHVF, release)
    return Dataset(
        release=release,
        regions=regions,
        zhvi=zhvi,
        market=pl.concat(market_frames) if market_frames else None,
        macro=pl.concat(macro_frames) if macro_frames else None,
        zhvf=zhvf_to_long(zhvf_wide) if zhvf_wide is not None else None,
        lags=publication_lags(),
    )


def build_metro_unemployment(
    release: str, regions: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame] | None:
    """Metro unemployment keyed by Zillow RegionID, plus the crosswalk used.

    Returns (series: region_id, date, value; crosswalk: region_id, region_name,
    state, size_rank, series_id, fred_name), or None without a snapshot.
    """
    source = FRED_METRO_UNEMPLOYMENT
    raw = read_fred_family(source, release)
    if raw is None:
        log.warning("no FRED metro unemployment snapshot for %s", release)
        return None
    long = fred_family_to_long(raw)
    per_series = long.group_by("series_id", "title").agg(pl.len().alias("n_obs"))
    crosswalk = match_metros(per_series, regions, source.title_prefix)
    n_series = long.get_column("series_id").n_unique()
    n_metros = regions.filter(pl.col("region_type") == "msa").height
    log.info(
        "metro unemployment: matched %d of %d FRED series to %d Zillow metros",
        crosswalk.height,
        n_series,
        n_metros,
    )
    series = long.join(crosswalk.select("region_id", "series_id"), on="series_id").select(
        "region_id", "date", "value"
    )
    crosswalk = crosswalk.join(
        regions.select("region_id", "region_name", "state", "size_rank"), on="region_id"
    ).select("region_id", "region_name", "state", "size_rank", "series_id", "fred_name")
    return series.sort("region_id", "date"), crosswalk.sort("size_rank")


def run(release: str) -> None:
    ds = load_raw(release)
    write_table(release, "regions", ds.regions)
    write_table(release, "zhvi", ds.zhvi)
    for name, df in (("market", ds.market), ("macro", ds.macro), ("zhvf", ds.zhvf)):
        if df is not None:
            write_table(release, name, df)

    metro = build_metro_unemployment(release, ds.regions)
    if metro is not None:
        write_table(release, "unemployment_metro", metro[0])
        write_table(release, "unemployment_metro_crosswalk", metro[1])

    _, excluded = filter_min_history(ds.zhvi, MIN_HISTORY_MONTHS)
    if excluded.height:
        write_table(release, "excluded_short_history", excluded)
        log.info(
            "%d series have < %d months of history and are excluded from training",
            excluded.height,
            MIN_HISTORY_MONTHS,
        )

    features = build_features(ds.zhvi, ds.regions, ds.market, ds.macro, ds.lags)
    path = write_table(release, "features", features)
    log.info(
        "release %s: %d regions, %d zhvi rows, %d feature columns -> %s",
        release,
        ds.regions.height,
        ds.zhvi.height,
        features.width - 2,
        path,
    )
