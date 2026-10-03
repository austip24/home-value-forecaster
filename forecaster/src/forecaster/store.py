"""Processed artifacts under data/processed/<release>/ (derived, safe to rebuild)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

from forecaster.config import processed_dir
from forecaster.sources import FRED_SOURCES, MARKET_SOURCES, ZHVI

TABLES = ("regions", "zhvi", "market", "macro", "zhvf")


@dataclass
class Dataset:
    """Everything the models need for one release, in long format."""

    release: str
    regions: pl.DataFrame
    zhvi: pl.DataFrame
    market: pl.DataFrame | None = None
    macro: pl.DataFrame | None = None
    zhvf: pl.DataFrame | None = None
    lags: dict[str, int] = field(default_factory=dict)
    # "zillow": `zhvi` holds metro home values. "fred": it holds the national macro
    # series, keyed by FredSource.region_id. "fred_metro": metro unemployment rates,
    # keyed by Zillow RegionID. The same pipeline forecasts all three.
    kind: str = "zillow"


def publication_lags() -> dict[str, int]:
    lags = {ZHVI.metric: ZHVI.publication_lag}
    lags.update({s.metric: s.publication_lag for s in MARKET_SOURCES})
    lags.update({s.metric: s.publication_lag for s in FRED_SOURCES})
    return lags


def table_path(release: str, name: str) -> Path:
    return processed_dir(release) / f"{name}.parquet"


def write_table(release: str, name: str, df: pl.DataFrame) -> Path:
    path = table_path(release, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)
    return path


def read_table(release: str, name: str) -> pl.DataFrame | None:
    path = table_path(release, name)
    return pl.read_parquet(path) if path.exists() else None


def load_dataset(release: str) -> Dataset:
    regions = read_table(release, "regions")
    zhvi = read_table(release, "zhvi")
    if regions is None or zhvi is None:
        raise FileNotFoundError(
            f"processed data for {release} not found; run `forecaster build-features` first"
        )
    return Dataset(
        release=release,
        regions=regions,
        zhvi=zhvi,
        market=read_table(release, "market"),
        macro=read_table(release, "macro"),
        zhvf=read_table(release, "zhvf"),
        lags=publication_lags(),
    )


def fred_regions() -> pl.DataFrame:
    """FRED series as forecast subjects, in the same shape as Zillow regions."""
    return pl.DataFrame(
        {
            "region_id": [s.region_id for s in FRED_SOURCES],
            "region_name": [s.label for s in FRED_SOURCES],
            "state": [None] * len(FRED_SOURCES),
            "region_type": ["series"] * len(FRED_SOURCES),
            "size_rank": [None] * len(FRED_SOURCES),
        },
        schema={
            "region_id": pl.Int64,
            "region_name": pl.Utf8,
            "state": pl.Utf8,
            "region_type": pl.Utf8,
            "size_rank": pl.Int64,
        },
    )


def load_fred_dataset(release: str) -> Dataset:
    """Macro series as the forecast target, ending at the release's ZHVI origin.

    The origin matches Zillow's (the month before the release), so both datasets
    forecast from the same point in time. That also drops the release month's
    partial mortgage-rate average.
    """
    from forecaster.ingest import expected_last_data_month

    macro = read_table(release, "macro")
    if macro is None or macro.is_empty():
        raise FileNotFoundError(
            f"no FRED data for {release}; set FRED_API_KEY, then run ingest and build-features"
        )
    origin = expected_last_data_month(release)
    ids = {s.metric: s.region_id for s in FRED_SOURCES}
    target = (
        macro.filter(pl.col("metric").is_in(list(ids)) & (pl.col("date") <= origin))
        .select(
            pl.col("metric").replace_strict(ids, return_dtype=pl.Int64).alias("region_id"),
            "date",
            "value",
        )
        .sort("region_id", "date")
    )
    return Dataset(
        release=release,
        regions=fred_regions(),
        zhvi=target,
        macro=macro,
        lags=publication_lags(),
        kind="fred",
    )


def load_fred_metro_dataset(release: str) -> Dataset:
    """Metro unemployment rates as the target, on Zillow's metro regions.

    Using Zillow's regions table keeps size tiers and showcase metros identical to
    the home-value dataset. The origin is the latest month in the snapshot: metro
    data lags, so it is usually a month before the Zillow origin.
    """
    target = read_table(release, "unemployment_metro")
    crosswalk = read_table(release, "unemployment_metro_crosswalk")
    regions = read_table(release, "regions")
    if target is None or crosswalk is None or regions is None:
        raise FileNotFoundError(
            f"no FRED metro unemployment for {release}; run ingest and build-features"
        )
    return Dataset(
        release=release,
        regions=regions.join(crosswalk.select("region_id"), on="region_id", how="semi"),
        zhvi=target,
        macro=read_table(release, "macro"),
        lags=publication_lags(),
        kind="fred_metro",
    )


def load(release: str, dataset: str) -> Dataset:
    if dataset == "zillow":
        return load_dataset(release)
    if dataset == "fred":
        return load_fred_dataset(release)
    if dataset == "fred_metro":
        return load_fred_metro_dataset(release)
    raise ValueError(f"unknown dataset {dataset!r}")


def target_names(ds: Dataset) -> pl.Expr:
    """What each forecast row predicts, for the forecasts table's `target` column."""
    if ds.kind == "fred":
        names = {s.region_id: s.metric for s in FRED_SOURCES}
        return pl.col("region_id").replace_strict(names, return_dtype=pl.Utf8)
    if ds.kind == "fred_metro":
        return pl.lit("unemployment")
    return pl.lit("zhvi")
