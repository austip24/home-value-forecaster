"""No feature or training row may depend on data published after its origin."""

from datetime import date

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from forecaster.models.gbm import training_frame
from forecaster.store import Dataset
from forecaster.transform.features import build_features
from forecaster.transform.history import add_months, published_by

ORIGINS = [date(2021, 6, 30), date(2022, 12, 31), date(2023, 9, 30)]


def _as_of(ds: Dataset, origin: date) -> pl.DataFrame:
    assert ds.market is not None and ds.macro is not None
    return build_features(
        ds.zhvi.filter(pl.col("date") <= origin),
        ds.regions,
        published_by(ds.market, origin, ds.lags),
        published_by(ds.macro, origin, ds.lags),
        ds.lags,
    )


@pytest.mark.parametrize("origin", ORIGINS)
def test_features_match_as_of_origin_build(dataset: Dataset, origin: date) -> None:
    """Rows up to the origin are identical whether or not later data exists."""
    full = build_features(
        dataset.zhvi, dataset.regions, dataset.market, dataset.macro, dataset.lags
    ).filter(pl.col("date") <= origin)
    assert_frame_equal(full, _as_of(dataset, origin), check_row_order=False)


@pytest.mark.parametrize("origin", ORIGINS)
def test_features_ignore_corrupted_future(dataset: Dataset, origin: date) -> None:
    """Scrambling every not-yet-published value leaves origin-time features unchanged."""
    assert dataset.market is not None and dataset.macro is not None

    def corrupt(df: pl.DataFrame, lag: pl.Expr | int) -> pl.DataFrame:
        lag_expr = pl.lit(lag) if isinstance(lag, int) else lag
        future = pl.col("date").dt.offset_by(pl.format("{}mo", lag_expr)).dt.month_end() > origin
        return df.with_columns(pl.when(future).then(pl.col("value") * 7.0).otherwise("value"))

    metric_lag = pl.col("metric").replace_strict(dataset.lags, return_dtype=pl.Int64)
    corrupted = build_features(
        corrupt(dataset.zhvi, 0),
        dataset.regions,
        corrupt(dataset.market, metric_lag),
        corrupt(dataset.macro, metric_lag),
        dataset.lags,
    )
    clean = build_features(
        dataset.zhvi, dataset.regions, dataset.market, dataset.macro, dataset.lags
    )
    at = pl.col("date") <= origin
    assert_frame_equal(clean.filter(at), corrupted.filter(at), check_row_order=False)


@pytest.mark.parametrize("horizon", [1, 3, 12])
def test_training_targets_are_realised_by_origin(dataset: Dataset, horizon: int) -> None:
    origin = date(2022, 12, 31)
    features = _as_of(dataset, origin)
    train = training_frame(features, dataset.zhvi, origin, horizon)
    assert train.height > 0
    latest = train.get_column("date").max()
    cutoff = pl.select(add_months(pl.lit(origin), -horizon)).item()
    assert latest == cutoff
