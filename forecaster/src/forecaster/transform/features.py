"""Feature matrix for the global model. Pure functions.

Every feature in the row for (region, t) uses only data whose data month plus
publication lag is <= t, so the row is knowable at origin t. `tests/test_leakage.py`
checks this by comparing features built from full vs. as-of-origin data.
"""

from __future__ import annotations

from collections.abc import Mapping

import polars as pl

from forecaster.config import NATIONAL_REGION_ID
from forecaster.transform.history import add_months

# How each market metric (Zillow, raw) is turned into features.
#   level: value itself; diff_k: change over k months; log_yoy: 12-month log change.
MARKET_TRANSFORMS: dict[str, tuple[str, ...]] = {
    "inventory": ("log_yoy",),
    "new_listings": ("log_yoy",),
    "new_pending": ("log_yoy",),
    "price_cut_share": ("level", "diff_3"),
    "days_to_pending": ("level", "diff_12"),
    "market_heat": ("level", "diff_3"),
    "sale_to_list": ("level", "diff_3"),
}

MACRO_TRANSFORMS: dict[str, tuple[str, ...]] = {
    "mortgage_rate": ("level", "diff_3", "diff_12"),
    "unemployment": ("level", "diff_12"),
    "cpi": ("log_yoy",),
}

_Y_LAGS = (1, 2, 3, 6, 12, 24)


def _shifted(df: pl.DataFrame, keys: list[str], value: str, months: int, name: str) -> pl.DataFrame:
    """Value observed at month d, re-keyed to month d + `months`."""
    return df.select(
        *keys,
        add_months(pl.col("date"), months).alias("date"),
        pl.col(value).alias(name),
    )


def _transform_exprs(prefix: str, transforms: tuple[str, ...]) -> list[pl.Expr]:
    exprs: list[pl.Expr] = []
    cur = pl.col(f"{prefix}__0")
    for t in transforms:
        if t == "level":
            exprs.append(cur.alias(prefix))
        elif t == "log_yoy":
            exprs.append((cur.log() - pl.col(f"{prefix}__12").log()).alias(f"{prefix}_log_yoy"))
        elif t.startswith("diff_"):
            k = t.removeprefix("diff_")
            exprs.append((cur - pl.col(f"{prefix}__{k}")).alias(f"{prefix}_{t}"))
        else:
            raise ValueError(f"unknown transform {t!r}")
    return exprs


def _needed_offsets(transforms: tuple[str, ...]) -> set[int]:
    offsets = {0}
    for t in transforms:
        if t == "log_yoy":
            offsets.add(12)
        elif t.startswith("diff_"):
            offsets.add(int(t.removeprefix("diff_")))
    return offsets


def _join_metric(
    base: pl.DataFrame,
    series: pl.DataFrame,
    keys: list[str],
    prefix: str,
    lag: int,
    transforms: tuple[str, ...],
) -> pl.DataFrame:
    """Attach lag-aware transforms of one metric's `value` column to `base`."""
    out = base
    for offset in sorted(_needed_offsets(transforms)):
        shifted = _shifted(series, keys, "value", lag + offset, f"{prefix}__{offset}")
        out = out.join(shifted, on=[*keys, "date"], how="left")
    helper_cols = [f"{prefix}__{o}" for o in _needed_offsets(transforms)]
    return out.with_columns(_transform_exprs(prefix, transforms)).drop(helper_cols)


def target_features(zhvi: pl.DataFrame) -> pl.DataFrame:
    """Momentum, volatility and drawdown features from the target series itself."""
    base = zhvi.select("region_id", "date", pl.col("value").log().alias("y")).sort(
        "region_id", "date"
    )
    out = base
    for k in _Y_LAGS:
        out = out.join(
            _shifted(base, ["region_id"], "y", k, f"y_l{k}"), on=["region_id", "date"], how="left"
        )
    y = pl.col("y")
    out = out.with_columns(
        (y - pl.col("y_l1")).alias("ret_1"),
        (pl.col("y_l1") - pl.col("y_l2")).alias("ret_1_l1"),
        (pl.col("y_l2") - pl.col("y_l3")).alias("ret_1_l2"),
        (y - pl.col("y_l3")).alias("ret_3"),
        (pl.col("y_l3") - pl.col("y_l6")).alias("ret_3_l3"),
        (y - pl.col("y_l6")).alias("ret_6"),
        (y - pl.col("y_l12")).alias("ret_12"),
        (pl.col("y_l12") - pl.col("y_l24")).alias("ret_12_l12"),
    ).sort("region_id", "date")
    out = out.with_columns(
        pl.col("ret_1")
        .rolling_std_by("date", window_size="12mo", min_samples=6)
        .over("region_id")
        .alias("vol_12"),
        (y - y.rolling_max_by("date", window_size="36mo").over("region_id")).alias("drawdown_36"),
    )
    out = out.with_columns((pl.col("ret_3") - pl.col("ret_3_l3")).alias("accel_3"))
    return out.drop([f"y_l{k}" for k in _Y_LAGS])


def build_features(
    zhvi: pl.DataFrame,
    regions: pl.DataFrame,
    market: pl.DataFrame | None,
    macro: pl.DataFrame | None,
    lags: Mapping[str, int],
) -> pl.DataFrame:
    """One row per (region_id, date) in `zhvi`, keyed so the row is knowable at `date`.

    zhvi:    region_id, date, value
    regions: region_id, size_rank
    market:  region_id, date, metric, value   (raw Zillow market metrics)
    macro:   date, metric, value              (national, monthly)
    lags:    metric -> publication lag in months
    """
    out = target_features(zhvi)

    national = out.filter(pl.col("region_id") == NATIONAL_REGION_ID).select(
        "date", pl.col("ret_1").alias("nat_ret_1"), pl.col("ret_12").alias("nat_ret_12")
    )
    out = out.join(national, on="date", how="left").with_columns(
        (pl.col("ret_12") - pl.col("nat_ret_12")).alias("rel_ret_12")
    )

    out = out.join(
        regions.select(
            "region_id", pl.col("size_rank").cast(pl.Float64).log1p().alias("log_size_rank")
        ),
        on="region_id",
        how="left",
    )

    if market is not None and market.height:
        present = set(market.get_column("metric").unique().to_list())
        for metric, transforms in MARKET_TRANSFORMS.items():
            if metric in present and metric in lags:
                series = market.filter(pl.col("metric") == metric).select(
                    "region_id", "date", "value"
                )
                out = _join_metric(out, series, ["region_id"], metric, lags[metric], transforms)
        if {"new_pending", "new_listings"} <= present and {
            "new_pending",
            "new_listings",
        } <= lags.keys():
            ratio = (
                market.filter(pl.col("metric").is_in(["new_pending", "new_listings"]))
                .pivot(on="metric", index=["region_id", "date"], values="value")
                .select(
                    "region_id",
                    "date",
                    (pl.col("new_pending") / pl.col("new_listings")).alias("value"),
                )
            )
            lag = max(lags["new_pending"], lags["new_listings"])
            out = _join_metric(out, ratio, ["region_id"], "pending_ratio", lag, ("level", "diff_3"))

    if macro is not None and macro.height:
        present = set(macro.get_column("metric").unique().to_list())
        for metric, transforms in MACRO_TRANSFORMS.items():
            if metric in present and metric in lags:
                series = macro.filter(pl.col("metric") == metric).select("date", "value")
                out = _join_metric(out, series, [], metric, lags[metric], transforms)

    return out.sort("region_id", "date")


def feature_columns(features: pl.DataFrame) -> list[str]:
    """Model inputs: everything except keys and the raw log level."""
    return [c for c in features.columns if c not in {"region_id", "date", "y"}]


def make_targets(zhvi: pl.DataFrame, horizon: int) -> pl.DataFrame:
    """`region_id, date, target`: log growth from month `date` to `date + horizon`."""
    y = zhvi.select("region_id", "date", pl.col("value").log().alias("y"))
    future = y.select(
        "region_id",
        add_months(pl.col("date"), -horizon).alias("date"),
        pl.col("y").alias("y_future"),
    )
    return y.join(future, on=["region_id", "date"], how="inner").select(
        "region_id", "date", (pl.col("y_future") - pl.col("y")).alias("target")
    )
