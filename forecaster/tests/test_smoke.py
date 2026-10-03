"""End-to-end pipeline on the tiny fixture dataset (no network, no database)."""

from pathlib import Path

import polars as pl

from forecaster import backtest, models, transform
from forecaster.backtest import BacktestConfig
from forecaster.publish import observations_frame
from forecaster.runs import latest_run
from forecaster.store import load_dataset, read_table
from tests.conftest import RELEASE


def test_pipeline_end_to_end(data_root: Path) -> None:
    transform.run(RELEASE)
    assert read_table(RELEASE, "features") is not None

    run = backtest.run(RELEASE, BacktestConfig(n_origins=3))
    assert latest_run(RELEASE) == run
    metrics = run.metrics()
    assert set(metrics.get_column("metric").unique()) == {"mase", "mape", "directional_accuracy"}
    assert set(metrics.get_column("horizon").unique()) == {1, 3, 12}
    assert "region:394976" in metrics.get_column("segment").to_list()
    assert run.config["data_vintage"] == "current"
    assert len(run.config["origins"]) == 3  # type: ignore[arg-type]

    models.run(RELEASE)
    fc = read_table(RELEASE, "forecasts")
    assert fc is not None
    assert set(fc.get_column("model").unique()) == {
        "naive",
        "seasonal_naive",
        "rw_drift",
        "auto_ets",
        "auto_arima",
        "lightgbm",
        "zhvf",
    }
    assert fc.get_column("release").unique().to_list() == [RELEASE]
    gbm = fc.filter(pl.col("model") == "lightgbm")
    assert gbm.get_column("lower").null_count() == 0  # conformal intervals from the backtest

    ds = load_dataset(RELEASE)
    obs = observations_frame(ds.zhvi, ds.market, ds.regions.select("region_id"), RELEASE)
    assert set(obs.get_column("metric").unique()) == {"zhvi", "inventory"}

    # FRED: same backtest and forecast steps, no benchmark, one segment per series.
    fred_run = backtest.run(RELEASE, BacktestConfig(n_origins=3), "fred")
    assert latest_run(RELEASE, "fred") == fred_run
    assert latest_run(RELEASE) == run  # Zillow runs are kept separately
    fred_segments = set(fred_run.metrics().get_column("segment").unique())
    assert {"all", "region:900001", "region:900002"} <= fred_segments
    assert not any(s.startswith("size:") for s in fred_segments)

    models.run(RELEASE, "fred")
    fred_fc = read_table(RELEASE, "forecasts_fred")
    assert fred_fc is not None
    assert set(fred_fc.get_column("model").unique()) == {
        "naive",
        "seasonal_naive",
        "rw_drift",
        "auto_ets",
        "auto_arima",
        "lightgbm",
    }
    assert set(fred_fc.get_column("horizon").unique()) == {1, 3, 12}
    assert fred_fc.filter(pl.col("model") == "lightgbm").get_column("lower").null_count() == 0
