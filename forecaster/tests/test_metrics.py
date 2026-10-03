from datetime import date

import polars as pl
import pytest

from forecaster.backtest import backtest_origins
from forecaster.backtest.metrics import naive_scale, row_errors, summarize

ORIGIN = date(2024, 1, 31)


def _preds(rows: list[tuple[int, str, int, float, float, float, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema=["region_id", "model", "horizon", "value", "y_origin", "scale", "actual"],
        orient="row",
    ).with_columns(pl.lit(ORIGIN).alias("origin_date"))


def test_row_errors() -> None:
    errs = row_errors(_preds([(1, "m", 1, 105.0, 100.0, 2.0, 110.0)]))
    assert errs.item(0, "scaled_abs_error") == pytest.approx(2.5)
    assert errs.item(0, "ape") == pytest.approx(5 / 110)
    assert errs.item(0, "direction_hit") == 1.0


def test_direction_miss() -> None:
    errs = row_errors(_preds([(1, "m", 1, 101.0, 100.0, 1.0, 99.0)]))
    assert errs.item(0, "direction_hit") == 0.0


def test_naive_scale() -> None:
    hist = pl.DataFrame(
        {
            "region_id": [1, 1, 1, 1],
            "date": [date(2023, 11, 30), date(2023, 12, 31), ORIGIN, date(2024, 2, 29)],
            "value": [100.0, 102.0, 106.0, 999.0],
        }
    )
    assert naive_scale(hist, ORIGIN).item(0, "scale") == pytest.approx(3.0)


def test_summarize_segments() -> None:
    preds = _preds(
        [
            (1, "naive", 1, 100.0, 100.0, 1.0, 101.0),
            (2, "naive", 1, 200.0, 200.0, 1.0, 203.0),
            (2, "zhvf", 1, 202.0, 200.0, 1.0, 203.0),
            (0, "naive", 1, 50.0, 50.0, 1.0, 51.0),
        ]
    )
    tiers = pl.DataFrame({"region_id": [0, 1, 2], "size_tier": ["national", "1-50", "201+"]})
    out = summarize(preds, tiers, showcase={2: "Two"})
    mase = out.filter(pl.col("metric") == "mase")

    def get(model: str, segment: str) -> float:
        return float(
            mase.filter((pl.col("model") == model) & (pl.col("segment") == segment)).item(
                0, "value"
            )
        )

    assert get("naive", "all") == pytest.approx(2.0)  # metros only: (1 + 3) / 2
    assert get("naive", "national") == pytest.approx(1.0)
    assert get("naive", "size:201+") == pytest.approx(3.0)
    assert get("naive", "region:2") == pytest.approx(3.0)
    # Head-to-head only on rows ZHVF also forecast.
    assert get("naive", "benchmark_matched") == pytest.approx(3.0)
    assert get("zhvf", "benchmark_matched") == pytest.approx(1.0)


def test_backtest_origins_leave_room_for_max_horizon() -> None:
    origins = backtest_origins(date(2026, 8, 31), 24, 12)
    assert len(origins) == 24
    assert origins[-1] == date(2025, 8, 31)
    assert origins[0] == date(2023, 9, 30)
