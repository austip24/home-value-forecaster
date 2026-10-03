"""Rolling-origin evaluation (MASE, MAPE, directional accuracy) per horizon."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import date

import polars as pl

from forecaster.backtest.metrics import naive_scale, summarize
from forecaster.config import (
    BACKTEST_ORIGINS,
    HORIZONS,
    INTERVAL_LEVEL,
    MIN_HISTORY_MONTHS,
    SHOWCASE_REGION_IDS,
)
from forecaster.ingest import expected_last_data_month
from forecaster.ingest.readers import read_zillow
from forecaster.models import ALL_MODELS, forecast_origin
from forecaster.models.benchmark import zhvf_levels
from forecaster.models.gbm import DEFAULT_PARAMS, NUM_BOOST_ROUND
from forecaster.runs import Run, save_run
from forecaster.segments import size_tiers
from forecaster.snapshots import list_releases
from forecaster.sources import ZHVF, ZHVI
from forecaster.store import Dataset, load
from forecaster.transform.features import build_features, feature_columns
from forecaster.transform.history import add_months
from forecaster.transform.reshape import wide_to_long, zhvf_to_long

log = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    n_origins: int = BACKTEST_ORIGINS
    horizons: tuple[int, ...] = HORIZONS
    models: tuple[str, ...] = ALL_MODELS
    level: int = INTERVAL_LEVEL
    min_history_months: int = MIN_HISTORY_MONTHS
    gbm_params: dict[str, object] = field(
        default_factory=lambda: {**DEFAULT_PARAMS, "num_boost_round": NUM_BOOST_ROUND}
    )


def backtest_origins(last_date: date, n_origins: int, max_horizon: int) -> list[date]:
    """The last `n_origins` monthly origins whose `max_horizon` target is already observed."""
    last_origin = add_months(pl.lit(last_date), -max_horizon)
    return (
        pl.select(
            pl.date_range(
                add_months(last_origin, -(n_origins - 1)), last_origin, "1mo", eager=False
            ).dt.month_end()
        )
        .to_series()
        .to_list()
    )


def vintage_zhvi(release: str) -> pl.DataFrame | None:
    wide = read_zillow(ZHVI, release)
    return wide_to_long(wide).select("region_id", "date", "value") if wide is not None else None


def vintage_releases_by_origin() -> dict[date, str]:
    """Snapshot release whose last ZHVI month is each origin (what was known then)."""
    return {expected_last_data_month(r): r for r in list_releases("zillow")}


def history_at(origin: date, ds: Dataset, vintages: dict[date, str]) -> tuple[pl.DataFrame, str]:
    """ZHVI as known at `origin`: its vintage snapshot if we have one, else current data."""
    release = vintages.get(origin)
    if release is not None and release != ds.release:
        zhvi = vintage_zhvi(release)
        if zhvi is not None:
            known = zhvi.join(ds.regions.select("region_id"), on="region_id", how="semi")
            return known.filter(pl.col("date") <= origin), release
    return ds.zhvi.filter(pl.col("date") <= origin), "current"


def benchmark_predictions(origins: Sequence[date], horizons: Sequence[int]) -> pl.DataFrame:
    """ZHVF level forecasts from every archived release whose origin is a backtest origin."""
    frames = []
    for release in list_releases("zillow"):
        origin = expected_last_data_month(release)
        if origin not in origins:
            continue
        zhvf_wide, zhvi = read_zillow(ZHVF, release), vintage_zhvi(release)
        if zhvf_wide is None or zhvi is None:
            continue
        levels = zhvf_levels(zhvf_to_long(zhvf_wide), zhvi).filter(
            pl.col("horizon").is_in(list(horizons))
        )
        base = zhvi.select(
            "region_id", pl.col("date").alias("origin_date"), pl.col("value").alias("y_origin")
        )
        frames.append(
            levels.join(base, on=["region_id", "origin_date"]).with_columns(
                pl.lit(release).alias("vintage")
            )
        )
    return pl.concat(frames) if frames else pl.DataFrame()


def run_backtest(
    ds: Dataset, config: BacktestConfig
) -> tuple[pl.DataFrame, pl.DataFrame, dict[str, object]]:
    """Returns (predictions with actuals, metrics, run metadata)."""
    last_date = ds.zhvi.get_column("date").max()
    assert isinstance(last_date, date)
    origins = backtest_origins(last_date, config.n_origins, max(config.horizons))
    # Archived snapshots and the ZHVF benchmark exist only for Zillow. FRED values
    # are snapshotted as known on release day (ALFRED), one vintage per release.
    is_zillow = ds.kind == "zillow"
    vintages = vintage_releases_by_origin() if is_zillow else {}
    log.info("backtest: %d origins %s .. %s", len(origins), origins[0], origins[-1])

    frames, scales, vintage_used, excluded_counts = [], [], {}, {}
    for i, origin in enumerate(origins, 1):
        history, vintage = history_at(origin, ds, vintages)
        preds, excluded = forecast_origin(
            history,
            ds.regions,
            ds.market,
            ds.macro,
            ds.lags,
            origin,
            config.horizons,
            config.models,
            config.level,
        )
        y_origin = history.filter(pl.col("date") == origin).select(
            "region_id", pl.col("value").alias("y_origin")
        )
        frames.append(
            preds.join(y_origin, on="region_id").with_columns(pl.lit(vintage).alias("vintage"))
        )
        scales.append(naive_scale(history, origin))
        vintage_used[origin.isoformat()] = vintage
        excluded_counts[origin.isoformat()] = excluded.height
        log.info(
            "origin %s (%d/%d): %d forecasts, vintage=%s, excluded=%d",
            origin,
            i,
            len(origins),
            preds.height,
            vintage,
            excluded.height,
        )

    bench = benchmark_predictions(origins, config.horizons) if is_zillow else pl.DataFrame()
    if bench.height:
        frames.append(bench.select(frames[0].columns))
    if is_zillow:
        log.info("ZHVF benchmark forecasts available at backtest origins: %d", bench.height)

    actuals = ds.zhvi.select(
        "region_id", pl.col("date").alias("target_date"), pl.col("value").alias("actual")
    )
    predictions = (
        pl.concat(frames)
        .join(pl.concat(scales), on=["region_id", "origin_date"], how="left")
        .join(actuals, on=["region_id", "target_date"], how="left")
    )
    # Each national FRED series gets its own segment; metro datasets (home values,
    # metro unemployment) use the showcase metros.
    showcase = (
        dict(ds.regions.select("region_id", "region_name").iter_rows())
        if ds.kind == "fred"
        else SHOWCASE_REGION_IDS
    )
    metrics = summarize(predictions, size_tiers(ds.regions), showcase)

    n_current = sum(v == "current" for v in vintage_used.values())
    meta: dict[str, object] = {
        **asdict(config),
        "dataset": ds.kind,
        "origins": [o.isoformat() for o in origins],
        "data_vintage": "current" if n_current == len(origins) else "mixed",
        "vintage_by_origin": vintage_used,
        "excluded_by_origin": excluded_counts,
        "publication_lags": ds.lags,
        "benchmark_forecasts": bench.height,
        "inputs": model_inputs(ds),
    }
    return predictions, metrics, meta


def model_inputs(ds: Dataset) -> dict[str, list[str]]:
    """Which data sources and features the global model had, for display and audit."""

    def metrics(df: pl.DataFrame | None) -> list[str]:
        return sorted(df.get_column("metric").unique().to_list()) if df is not None else []

    features = build_features(ds.zhvi, ds.regions, ds.market, ds.macro, ds.lags)
    return {
        "market": metrics(ds.market),
        "macro": metrics(ds.macro),
        "features": feature_columns(features),
    }


def stage_report(metrics: pl.DataFrame, models: Sequence[str]) -> pl.DataFrame:
    """MASE by model x horizon on all metros, with best model per horizon."""
    mase = metrics.filter((pl.col("segment") == "all") & (pl.col("metric") == "mase"))
    order = {m: i for i, m in enumerate([*models, "zhvf"])}
    return (
        mase.pivot(on="horizon", index="model", values="value")
        .with_columns(pl.col("model").replace_strict(order, default=99).alias("_o"))
        .sort("_o")
        .drop("_o")
    )


def run(release: str, config: BacktestConfig | None = None, dataset: str = "zillow") -> Run:
    config = config or BacktestConfig()
    ds = load(release, dataset)
    predictions, metrics, meta = run_backtest(ds, config)
    run_ = save_run(release, meta, predictions, metrics, dataset)
    log.info("saved %s backtest run %s -> %s", dataset, run_.run_id, run_.path)
    if meta["data_vintage"] == "current":
        log.warning(
            "all origins used current-vintage data (no archived snapshots); results are "
            "labelled data_vintage=current"
        )
    subjects = "all metros" if dataset == "zillow" else f"all {dataset} series"
    with pl.Config(tbl_rows=20, float_precision=4):
        print(f"\nMASE, {subjects} (run {run_.run_id}):")
        print(stage_report(metrics, config.models))
    return run_
