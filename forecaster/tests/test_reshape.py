from datetime import date

import polars as pl

from forecaster.transform.reshape import (
    LONG_COLUMNS,
    fred_to_monthly,
    regions_from_wide,
    wide_to_long,
    zhvf_to_long,
)

WIDE = pl.DataFrame(
    {
        "RegionID": ["1", "2"],
        "SizeRank": ["0", "5"],
        "RegionName": ["United States", "Phoenix, AZ"],
        "RegionType": ["country", "msa"],
        "StateName": [None, "AZ"],
        "2024-01-31": ["100.0", None],
        "2024-02-29": ["101.5", "200.0"],
    }
)


def test_wide_to_long_shape_and_types() -> None:
    long = wide_to_long(WIDE)
    assert long.columns == LONG_COLUMNS
    assert long.schema["region_id"] == pl.Int64
    assert long.schema["date"] == pl.Date
    # Null cells are dropped, not kept as missing rows.
    assert long.height == 3
    phoenix = long.filter(pl.col("region_id") == 2)
    assert phoenix.get_column("date").to_list() == [date(2024, 2, 29)]


def test_regions_from_wide() -> None:
    regions = regions_from_wide(WIDE)
    assert regions.get_column("size_rank").to_list() == [0, 5]
    assert regions.get_column("region_type").to_list() == ["country", "msa"]


def test_zhvf_to_long_computes_horizons() -> None:
    wide = pl.DataFrame(
        {
            "RegionID": ["2"],
            "BaseDate": ["2023-12-31"],
            "2024-01-31": ["0.5"],
            "2024-03-31": ["1.0"],
            "2024-12-31": ["-2.0"],
        }
    )
    long = zhvf_to_long(wide).sort("horizon")
    assert long.get_column("horizon").to_list() == [1, 3, 12]
    assert long.get_column("growth_pct").to_list() == [0.5, 1.0, -2.0]
    assert long.get_column("origin_date").unique().to_list() == [date(2023, 12, 31)]


def test_fred_to_monthly_averages_weekly_to_month_end() -> None:
    raw = pl.DataFrame(
        {"date": ["2024-01-04", "2024-01-11", "2024-02-01"], "value": ["6.0", "7.0", "."]}
    )
    monthly = fred_to_monthly(raw, "mortgage_rate")
    assert monthly.to_dicts() == [
        {"date": date(2024, 1, 31), "metric": "mortgage_rate", "value": 6.5}
    ]
