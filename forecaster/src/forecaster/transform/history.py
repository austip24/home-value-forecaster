"""History filters: what was knowable at an origin, and which series are long enough."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import polars as pl


def add_months(col: pl.Expr, months: int) -> pl.Expr:
    """Shift month-end dates by whole months, staying on month-end."""
    return col.dt.offset_by(f"{months}mo").dt.month_end()


def published_by(df: pl.DataFrame, origin: date, lags: Mapping[str, int] | int) -> pl.DataFrame:
    """Rows whose data month plus publication lag is on or before `origin`.

    `lags` is either one lag for the whole frame or a per-`metric` mapping; metrics
    missing from the mapping are dropped rather than guessed.
    """
    if isinstance(lags, int):
        return df.filter(add_months(pl.col("date"), lags) <= origin)
    lag = pl.col("metric").replace_strict(dict(lags), default=None, return_dtype=pl.Int64)
    return df.filter(
        lag.is_not_null()
        & (pl.col("date").dt.offset_by(pl.format("{}mo", lag)).dt.month_end() <= origin)
    )


def filter_min_history(
    long: pl.DataFrame, min_months: int, origin: date | None = None
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Split series into (kept rows, excluded summary).

    A series is kept when it has at least `min_months` observations and, if `origin` is
    given, is still current at the origin (its last observation is the origin month).
    """
    stats = long.group_by("region_id").agg(
        pl.len().alias("n_months"), pl.col("date").max().alias("last_date")
    )
    ok = pl.col("n_months") >= min_months
    if origin is not None:
        ok = ok & (pl.col("last_date") == origin)
    kept_ids = stats.filter(ok).select("region_id")
    excluded = stats.filter(~ok).sort("region_id")
    return long.join(kept_ids, on="region_id", how="semi"), excluded
