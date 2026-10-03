from datetime import date
from pathlib import Path

import pytest

from forecaster.ingest import _write_atomic, expected_last_data_month, fred_as_of, last_date_column


def test_expected_last_data_month() -> None:
    assert expected_last_data_month("2026-09") == date(2026, 8, 31)
    assert expected_last_data_month("2024-03") == date(2024, 2, 29)


def test_last_date_column() -> None:
    header = ["RegionID", "RegionName", "2026-07-31", "2026-08-31"]
    assert last_date_column(header) == date(2026, 8, 31)
    assert last_date_column(["RegionID"]) is None


def test_fred_as_of_caps_at_today() -> None:
    assert fred_as_of("2026-09", today=date(2026, 10, 2)) == date(2026, 9, 16)
    assert fred_as_of("2026-10", today=date(2026, 10, 2)) == date(2026, 10, 2)


def test_snapshots_are_never_overwritten(tmp_path: Path) -> None:
    dest = tmp_path / "zillow" / "2026-09" / "zhvi.csv"
    _write_atomic(dest, b"original")
    with pytest.raises(FileExistsError):
        _write_atomic(dest, b"replacement")
    assert dest.read_bytes() == b"original"
    assert [p.name for p in dest.parent.iterdir()] == ["zhvi.csv"]
