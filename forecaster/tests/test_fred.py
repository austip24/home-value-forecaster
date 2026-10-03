"""FRED macro series run through the same pipeline as Zillow metros."""

from datetime import date
from pathlib import Path

import polars as pl

from forecaster import transform
from forecaster.publish import fred_observations
from forecaster.store import load_fred_dataset
from tests.conftest import RELEASE


def test_fred_dataset_ends_at_release_origin(data_root: Path) -> None:
    transform.run(RELEASE)
    ds = load_fred_dataset(RELEASE)
    assert ds.kind == "fred"
    # Fixture mortgage data runs into Jan 2024 (a partial month in the 2024-01
    # release); the target stops at the shared origin, Dec 2023.
    assert ds.zhvi.get_column("date").max() == date(2023, 12, 31)
    assert set(ds.zhvi.get_column("region_id").unique()) == {900001, 900002}
    assert set(ds.regions.get_column("region_type").unique()) == {"series"}


def test_fred_observations_use_series_metric_names(data_root: Path) -> None:
    transform.run(RELEASE)
    obs = fred_observations(load_fred_dataset(RELEASE), RELEASE)
    assert set(obs.get_column("metric").unique()) == {"mortgage_rate", "unemployment"}
    assert obs.get_column("release").unique().to_list() == [RELEASE]
    assert obs.filter(pl.col("region_id") == 900001).height > 36


def test_metro_unemployment_runs_through_the_pipeline(data_root: Path) -> None:
    from forecaster import backtest, models
    from forecaster.backtest import BacktestConfig
    from forecaster.runs import latest_run
    from forecaster.store import load_fred_metro_dataset, read_table

    transform.run(RELEASE)
    crosswalk = read_table(RELEASE, "unemployment_metro_crosswalk")
    assert crosswalk is not None
    # Phoenix and the multi-state New York metro match; Abilene has no Zillow metro.
    assert dict(crosswalk.select("region_id", "series_id").iter_rows()) == {
        394976: "PHOE004UR",
        394913: "NEWY636UR",
    }

    ds = load_fred_metro_dataset(RELEASE)
    assert ds.kind == "fred_metro"
    # Metro data lags: its origin is the latest month in the snapshot.
    assert ds.zhvi.get_column("date").max() == date(2023, 11, 30)

    run = backtest.run(RELEASE, BacktestConfig(n_origins=3), "fred_metro")
    assert latest_run(RELEASE, "fred_metro") == run
    segments = set(run.metrics().get_column("segment").unique())
    assert {"all", "size:1-50", "region:394976"} <= segments  # Zillow-style segments

    models.run(RELEASE, "fred_metro")
    fc = read_table(RELEASE, "forecasts_fred_metro")
    assert fc is not None
    assert fc.get_column("target").unique().to_list() == ["unemployment"]
    assert set(fc.get_column("region_id").unique()) == {394976, 394913}
    assert fc.filter(pl.col("model") == "lightgbm").get_column("lower").null_count() == 0
