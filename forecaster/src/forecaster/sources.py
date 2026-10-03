"""Catalog of raw inputs: where they come from, what they are called on disk, and when
each month's value becomes public.

`publication_lag` is the number of months between a data month and the first origin at
which it may be used. An origin is the last ZHVI month in a release, so ZHVI itself has
lag 0: the release on ~the 16th of M+1 contains ZHVI for M. A series with lag 1 is only
trusted one release later. When in doubt, lag is rounded up.
"""

from __future__ import annotations

from dataclasses import dataclass

ZILLOW_BASE_URL = "https://files.zillowstatic.com/research/public_csvs"


@dataclass(frozen=True)
class ZillowSource:
    metric: str
    path: str  # relative to ZILLOW_BASE_URL
    stem: str  # on-disk name without extension: <metric>_<geo>_<hometype>_<adjustment>
    publication_lag: int
    required: bool = False

    @property
    def url(self) -> str:
        return f"{ZILLOW_BASE_URL}/{self.path}"


@dataclass(frozen=True)
class FredSource:
    metric: str
    series_id: str
    stem: str
    publication_lag: int
    # Forecast-subject id, so FRED series flow through the same region-keyed pipeline
    # as metros. 900001+ never collides with Zillow RegionIDs in the shared regions table.
    region_id: int
    label: str


ZHVI = ZillowSource(
    metric="zhvi",
    path="zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
    stem="zhvi_metro_allhomes_sm_sa",
    publication_lag=0,
    required=True,
)

ZHVF = ZillowSource(
    metric="zhvf",
    path="zhvf_growth/Metro_zhvf_growth_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
    stem="zhvf_metro_allhomes_sm_sa",
    publication_lag=0,
)

# Market features: raw (unsmoothed) versions only, to avoid smoothing-window leakage.
# Listing-side metrics publish with ZHVI; sales-side metrics (sale-to-list) lag a month.
MARKET_SOURCES: tuple[ZillowSource, ...] = (
    ZillowSource(
        "inventory",
        "invt_fs/Metro_invt_fs_uc_sfrcondo_month.csv",
        "inventory_metro_allhomes_raw",
        publication_lag=0,
    ),
    ZillowSource(
        "new_listings",
        "new_listings/Metro_new_listings_uc_sfrcondo_month.csv",
        "new_listings_metro_allhomes_raw",
        publication_lag=0,
    ),
    ZillowSource(
        "new_pending",
        "new_pending/Metro_new_pending_uc_sfrcondo_month.csv",
        "new_pending_metro_allhomes_raw",
        publication_lag=0,
    ),
    ZillowSource(
        "price_cut_share",
        "perc_listings_price_cut/Metro_perc_listings_price_cut_uc_sfrcondo_month.csv",
        "price_cut_share_metro_allhomes_raw",
        publication_lag=0,
    ),
    ZillowSource(
        "days_to_pending",
        "mean_doz_pending/Metro_mean_doz_pending_uc_sfrcondo_month.csv",
        "days_to_pending_metro_allhomes_raw",
        publication_lag=0,
    ),
    ZillowSource(
        "market_heat",
        "market_temp_index/Metro_market_temp_index_uc_sfrcondo_month.csv",
        "market_heat_metro_allhomes_raw",
        publication_lag=0,
    ),
    ZillowSource(
        "sale_to_list",
        "mean_sale_to_list/Metro_mean_sale_to_list_uc_sfrcondo_month.csv",
        "sale_to_list_metro_allhomes_raw",
        publication_lag=1,
    ),
)

ZILLOW_SOURCES: tuple[ZillowSource, ...] = (ZHVI, ZHVF, *MARKET_SOURCES)

# Mortgage rates are weekly and effectively real-time. CPI and unemployment for month M
# usually publish before the 16th of M+1, but not reliably (e.g. shutdown delays), so
# they are held back one month.
FRED_SOURCES: tuple[FredSource, ...] = (
    FredSource(
        "mortgage_rate",
        "MORTGAGE30US",
        "mortgage30_national_na_nsa",
        publication_lag=0,
        region_id=900001,
        label="30-year mortgage rate",
    ),
    FredSource(
        "unemployment",
        "UNRATE",
        "unrate_national_na_sa",
        publication_lag=1,
        region_id=900002,
        label="Unemployment rate",
    ),
    FredSource(
        "cpi",
        "CPIAUCSL",
        "cpi_national_na_sa",
        publication_lag=1,
        region_id=900003,
        label="Consumer Price Index",
    ),
)


@dataclass(frozen=True)
class FredMetroSource:
    """A family of FRED series, one per metro, found by FRED tag search."""

    metric: str
    stem: str
    tag_names: str  # FRED tags identifying the family, ";"-separated
    title_prefix: str  # e.g. "Unemployment Rate in " — the metro name follows
    # BLS publishes metro unemployment for month M about five weeks later, so on
    # release day (~16th of M+1) the latest metro month is usually M-1.
    publication_lag: int


# Smoothed seasonally adjusted, to match national UNRATE and the non-seasonal models.
FRED_METRO_UNEMPLOYMENT = FredMetroSource(
    metric="unemployment_metro",
    stem="unrate_metro_na_sa",
    tag_names="msa;unemployment;rate;monthly;sa",
    title_prefix="Unemployment Rate in ",
    publication_lag=1,
)
