import math
from datetime import date

import polars as pl
import pytest

from forecaster.store import Dataset
from forecaster.transform.features import build_features, feature_columns, make_targets


def test_target_momentum_features(dataset: Dataset) -> None:
    feats = build_features(dataset.zhvi, dataset.regions, None, None, dataset.lags)
    zhvi = dataset.zhvi.filter(pl.col("region_id") == 394976).sort("date")
    v = zhvi.get_column("value").to_list()
    row = feats.filter((pl.col("region_id") == 394976) & (pl.col("date") == date(2023, 12, 31)))
    assert row.item(0, "ret_1") == pytest.approx(math.log(v[-1] / v[-2]))
    assert row.item(0, "ret_12") == pytest.approx(math.log(v[-1] / v[-13]))
    assert row.item(0, "ret_1_l1") == pytest.approx(math.log(v[-2] / v[-3]))
    assert row.item(0, "drawdown_36") <= 0


def test_market_and_macro_features_use_publication_lag(dataset: Dataset) -> None:
    lags = {**dataset.lags, "inventory": 1, "unemployment": 1}
    feats = build_features(dataset.zhvi, dataset.regions, dataset.market, dataset.macro, lags)
    assert dataset.market is not None and dataset.macro is not None
    origin, prior = date(2023, 12, 31), date(2023, 11, 30)

    inv = dataset.market.filter((pl.col("region_id") == 394976) & (pl.col("metric") == "inventory"))
    inv_prior = inv.filter(pl.col("date") == prior).item(0, "value")
    inv_year_before = inv.filter(pl.col("date") == date(2022, 11, 30)).item(0, "value")
    row = feats.filter((pl.col("region_id") == 394976) & (pl.col("date") == origin))
    assert row.item(0, "inventory_log_yoy") == pytest.approx(math.log(inv_prior / inv_year_before))

    unrate = dataset.macro.filter(pl.col("metric") == "unemployment")
    assert row.item(0, "unemployment") == unrate.filter(pl.col("date") == prior).item(0, "value")


def test_feature_columns_exclude_keys(dataset: Dataset) -> None:
    feats = build_features(
        dataset.zhvi, dataset.regions, dataset.market, dataset.macro, dataset.lags
    )
    cols = feature_columns(feats)
    assert {"region_id", "date", "y"}.isdisjoint(cols)
    assert {"ret_1", "nat_ret_12", "mortgage_rate", "inventory_log_yoy"} <= set(cols)


def test_make_targets_is_forward_log_growth() -> None:
    zhvi = pl.DataFrame(
        {
            "region_id": [1, 1, 1, 1],
            "date": [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31), date(2024, 4, 30)],
            "value": [100.0, 110.0, 121.0, 133.1],
        }
    )
    targets = make_targets(zhvi, 3)
    assert targets.height == 1
    assert targets.item(0, "date") == date(2024, 1, 31)
    assert targets.item(0, "target") == pytest.approx(math.log(1.331))
