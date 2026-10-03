"""Shared fixtures: a throwaway data/ tree populated from tests/fixtures/ (release 2024-01)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from forecaster import config
from forecaster.store import Dataset

FIXTURES = Path(__file__).parent / "fixtures"
RELEASE = "2024-01"

ZILLOW_FILES = (
    "zhvi_metro_allhomes_sm_sa.csv",
    "zhvf_metro_allhomes_sm_sa.csv",
    "inventory_metro_allhomes_raw.csv",
)
FRED_FILES = (
    "mortgage30_national_na_nsa.csv",
    "unrate_national_na_sa.csv",
    "unrate_metro_na_sa.csv",
)


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the pipeline at tmp_path/{raw,processed} holding the fixture snapshot."""
    raw, processed = tmp_path / "raw", tmp_path / "processed"
    for source, names in (("zillow", ZILLOW_FILES), ("fred", FRED_FILES)):
        dest = raw / source / RELEASE
        dest.mkdir(parents=True)
        for name in names:
            shutil.copy(FIXTURES / name, dest / name)
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(config, "PROCESSED_DIR", processed)
    monkeypatch.setattr(config, "N_JOBS", 1)
    return tmp_path


@pytest.fixture
def dataset(data_root: Path) -> Dataset:
    from forecaster.transform import load_raw

    return load_raw(RELEASE)
