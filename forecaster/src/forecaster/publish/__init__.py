"""Write forecasts, metrics, and run metadata to Postgres."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from typing import Any

import polars as pl
import psycopg

from forecaster.config import DATABASE_URL, DATASETS, MIGRATIONS_DIR, forecasts_table
from forecaster.runs import Run, latest_run
from forecaster.sources import FRED_SOURCES
from forecaster.store import Dataset, load_dataset, load_fred_dataset, read_table

log = logging.getLogger(__name__)

# Market signals shown on the metro detail page, published alongside ZHVI.
PUBLISHED_MARKET_METRICS = ("inventory", "price_cut_share", "days_to_pending", "new_listings")


def connect(url: str = DATABASE_URL) -> psycopg.Connection[Any]:
    if not url:
        raise RuntimeError("DATABASE_URL is not set (see forecaster/.env.example)")
    return psycopg.connect(url)


def migrate(conn: psycopg.Connection[Any]) -> list[str]:
    """Apply forecaster/migrations/*.sql in name order, once each."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    new = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.stem in applied:
            continue
        conn.execute(path.read_text())
        conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,))
        new.append(path.stem)
    conn.commit()
    return new


def _copy(
    conn: psycopg.Connection[Any],
    table: str,
    columns: Sequence[str],
    rows: Iterable[tuple[Any, ...]],
) -> int:
    n = 0
    with conn.cursor() as cur, cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as cp:
        for row in rows:
            cp.write_row(row)
            n += 1
    return n


def observations_frame(
    zhvi: pl.DataFrame, market: pl.DataFrame | None, region_ids: pl.DataFrame, release: str
) -> pl.DataFrame:
    frames = [zhvi.select("region_id", "date", pl.lit("zhvi").alias("metric"), "value")]
    if market is not None:
        frames.append(
            market.filter(pl.col("metric").is_in(PUBLISHED_MARKET_METRICS)).select(
                "region_id", "date", "metric", "value"
            )
        )
    return (
        pl.concat(frames)
        .join(region_ids, on="region_id", how="semi")
        .with_columns(pl.lit(release).alias("release"))
    )


def publish_run(conn: psycopg.Connection[Any], run: Run) -> int:
    conn.execute(
        "INSERT INTO runs (run_id, release, git_sha, config, created_at)"
        " VALUES (%s, %s, %s, %s::jsonb, %s) ON CONFLICT (run_id) DO NOTHING",
        (run.run_id, run.release, run.git_sha, json.dumps(run.config, default=str), run.created_at),
    )
    conn.execute("DELETE FROM backtest_metrics WHERE run_id = %s", (run.run_id,))
    cols = ["run_id", "model", "horizon", "metric", "value", "segment"]
    metrics = run.metrics().drop_nulls("value").with_columns(pl.lit(run.run_id).alias("run_id"))
    return _copy(conn, "backtest_metrics", cols, metrics.select(cols).iter_rows())


def fred_observations(ds: Dataset, release: str) -> pl.DataFrame:
    """FRED series as observations, one metric per series (e.g. mortgage_rate)."""
    names = {src.region_id: src.metric for src in FRED_SOURCES}
    return ds.zhvi.select(
        "region_id",
        "date",
        pl.col("region_id").replace_strict(names, return_dtype=pl.Utf8).alias("metric"),
        "value",
        pl.lit(release).alias("release"),
    )


def run(release: str) -> None:
    ds = load_dataset(release)
    forecasts = read_table(release, forecasts_table("zillow"))
    if forecasts is None:
        raise FileNotFoundError(f"no forecasts for {release}; run `forecaster forecast` first")
    runs = [r for r in (latest_run(release, d) for d in DATASETS) if r is not None]

    regions = ds.regions
    obs = observations_frame(ds.zhvi, ds.market, ds.regions.select("region_id"), release)

    # National FRED series ride along as extra subjects (region_id 900001+).
    try:
        fred = load_fred_dataset(release)
    except FileNotFoundError:
        fred = None
    if fred is not None:
        regions = pl.concat([regions, fred.regions.select(regions.columns)])
        obs = pl.concat([obs, fred_observations(fred, release).select(obs.columns)])

    # Metro unemployment uses the Zillow metros' own region_id, told apart from
    # home values by `metric` (observations) and `target` (forecasts).
    metro = read_table(release, "unemployment_metro")
    if metro is not None:
        obs = pl.concat(
            [
                obs,
                metro.select(
                    "region_id",
                    "date",
                    pl.lit("unemployment").alias("metric"),
                    "value",
                    pl.lit(release).alias("release"),
                ).join(regions.select("region_id"), on="region_id", how="semi"),
            ]
        )

    for dataset in DATASETS[1:]:
        extra = read_table(release, forecasts_table(dataset))
        if extra is not None:
            forecasts = pl.concat([forecasts, extra.select(forecasts.columns)])

    with connect() as conn:
        for version in migrate(conn):
            log.info("applied migration %s", version)

        region_cols = ["region_id", "region_name", "state", "size_rank"]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO regions (region_id, region_name, state, size_rank)"
                " VALUES (%s, %s, %s, %s) ON CONFLICT (region_id) DO UPDATE SET"
                " region_name = EXCLUDED.region_name, state = EXCLUDED.state,"
                " size_rank = EXCLUDED.size_rank",
                list(regions.select(region_cols).iter_rows()),
            )

        conn.execute("DELETE FROM observations WHERE release = %s", (release,))
        n_obs = _copy(
            conn,
            "observations",
            ["region_id", "date", "metric", "value", "release"],
            obs.iter_rows(),
        )

        fc_cols = [
            "region_id",
            "origin_date",
            "target_date",
            "horizon",
            "model",
            "value",
            "lower",
            "upper",
            "target",
            "release",
        ]
        conn.execute("DELETE FROM forecasts WHERE release = %s", (release,))
        n_fc = _copy(conn, "forecasts", fc_cols, forecasts.select(fc_cols).iter_rows())

        n_metrics = sum(publish_run(conn, r) for r in runs)
        conn.commit()

    log.info(
        "published release %s: %d regions, %d observations, %d forecasts, %d metrics (runs %s)",
        release,
        regions.height,
        n_obs,
        n_fc,
        n_metrics,
        ", ".join(r.run_id for r in runs) or "none",
    )
