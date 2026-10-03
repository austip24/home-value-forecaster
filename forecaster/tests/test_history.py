from datetime import date

import polars as pl

from forecaster.transform.history import add_months, filter_min_history, published_by


def test_add_months_stays_on_month_end() -> None:
    out = pl.select(
        add_months(pl.lit(date(2024, 1, 31)), 1).alias("a"),
        add_months(pl.lit(date(2024, 2, 29)), 1).alias("b"),
        add_months(pl.lit(date(2024, 3, 31)), -12).alias("c"),
    ).row(0)
    assert out == (date(2024, 2, 29), date(2024, 3, 31), date(2023, 3, 31))


def test_published_by_respects_per_metric_lag() -> None:
    df = pl.DataFrame(
        {
            "date": [date(2024, 1, 31), date(2024, 1, 31), date(2023, 12, 31), date(2024, 1, 31)],
            "metric": ["fast", "slow", "slow", "unknown"],
            "value": [1.0, 2.0, 3.0, 4.0],
        }
    )
    known = published_by(df, date(2024, 1, 31), {"fast": 0, "slow": 1})
    # slow/Jan is not out until the Feb origin; unknown metrics are dropped.
    assert sorted(known.get_column("value").to_list()) == [1.0, 3.0]


def test_filter_min_history_drops_short_and_stale() -> None:
    def months(n: int, end: date) -> list[date]:
        return (
            pl.date_range(add_months(pl.lit(end), -(n - 1)), end, "1mo", eager=True)
            .dt.month_end()
            .to_list()
        )

    end = date(2024, 12, 31)
    long = pl.concat(
        [
            pl.DataFrame({"region_id": 1, "date": months(36, end), "value": 1.0}),
            pl.DataFrame({"region_id": 2, "date": months(35, end), "value": 1.0}),
            pl.DataFrame({"region_id": 3, "date": months(40, date(2024, 11, 30)), "value": 1.0}),
        ]
    )
    kept, excluded = filter_min_history(long, 36, origin=end)
    assert kept.get_column("region_id").unique().to_list() == [1]
    assert excluded.get_column("region_id").to_list() == [2, 3]
