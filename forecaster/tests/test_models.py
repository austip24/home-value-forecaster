from datetime import date

import polars as pl
import pytest

from forecaster.models import forecast_origin
from forecaster.models.benchmark import zhvf_levels
from forecaster.models.intervals import apply_conformal, conformal_quantiles
from forecaster.store import Dataset

ORIGIN = date(2023, 12, 31)


def test_zhvf_levels_grow_from_origin_value() -> None:
    zhvf = pl.DataFrame(
        {
            "region_id": [1, 1],
            "origin_date": [ORIGIN, ORIGIN],
            "target_date": [date(2024, 1, 31), date(2024, 12, 31)],
            "horizon": [1, 12],
            "growth_pct": [1.0, -5.0],
        }
    )
    zhvi = pl.DataFrame({"region_id": [1], "date": [ORIGIN], "value": [200.0]})
    out = zhvf_levels(zhvf, zhvi).sort("horizon")
    assert out.get_column("value").to_list() == pytest.approx([202.0, 190.0])
    assert out.get_column("model").unique().to_list() == ["zhvf"]


def test_conformal_fills_only_missing_intervals() -> None:
    errors = pl.DataFrame(
        {
            "model": ["g"] * 5,
            "horizon": [1] * 5,
            "size_tier": ["1-50"] * 5,
            "log_error": [-0.02, -0.01, 0.0, 0.01, 0.02],
        }
    )
    q = conformal_quantiles(errors, level=80)
    fc = pl.DataFrame(
        {
            "region_id": [1, 1],
            "origin_date": [ORIGIN, ORIGIN],
            "target_date": [date(2024, 1, 31)] * 2,
            "horizon": [1, 1],
            "model": ["g", "s"],
            "value": [100.0, 100.0],
            "lower": [None, 90.0],
            "upper": [None, 110.0],
        }
    )
    tiers = pl.DataFrame({"region_id": [1], "size_tier": ["1-50"]})
    out = apply_conformal(fc, q, tiers).sort("model")
    g, s = out.row(0, named=True), out.row(1, named=True)
    assert g["lower"] < 100 < g["upper"]
    assert (s["lower"], s["upper"]) == (90.0, 110.0)


def test_forecast_origin_all_models(dataset: Dataset) -> None:
    fc, excluded = forecast_origin(
        dataset.zhvi, dataset.regions, dataset.market, dataset.macro, dataset.lags, ORIGIN
    )
    # The 20-month "Tiny" series is excluded; three regions x six models x three horizons.
    assert excluded.get_column("region_id").to_list() == [999001]
    assert fc.height == 3 * 6 * 3
    assert set(fc.get_column("horizon").unique()) == {1, 3, 12}
    assert fc.filter(pl.col("target_date") <= ORIGIN).is_empty()
    assert fc.get_column("value").is_finite().all()
    stats = fc.filter(pl.col("model") != "lightgbm")
    assert (stats.get_column("lower") <= stats.get_column("value")).all()
    assert (stats.get_column("value") <= stats.get_column("upper")).all()
