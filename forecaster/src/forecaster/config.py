"""Paths and settings shared across the pipeline."""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# forecaster/src/forecaster/config.py -> repo root is three levels above src/
REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MIGRATIONS_DIR = REPO_ROOT / "forecaster" / "migrations"

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Worker processes/threads for model fitting; -1 uses every core.
N_JOBS = int(os.getenv("FORECASTER_N_JOBS", "-1"))

# Forecast horizons in months ahead of the origin (the last observed ZHVI month).
HORIZONS: tuple[int, ...] = (1, 3, 12)
MAX_HORIZON = max(HORIZONS)

# Series with fewer observed months than this at an origin are excluded from training.
MIN_HISTORY_MONTHS = 36

# Central prediction interval width, in percent.
INTERVAL_LEVEL = 80

# Rolling-origin backtest: number of monthly origins, evaluated at every horizon.
BACKTEST_ORIGINS = 24

# Zillow RegionIDs always reported as their own segment.
SHOWCASE_REGION_IDS: dict[int, str] = {
    394976: "Phoenix, AZ",
    394913: "New York, NY",
    753899: "Los Angeles, CA",
    394355: "Austin, TX",
    394974: "Philadelphia, PA",
}
NATIONAL_REGION_ID = 102001

_RELEASE_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def validate_release(release: str) -> str:
    """Ensure a release label looks like YYYY-MM."""
    if not _RELEASE_RE.match(release):
        raise ValueError(f"release must be YYYY-MM, got {release!r}")
    return release


def release_month(release: str) -> date:
    """First day of the release month."""
    year, month = validate_release(release).split("-")
    return date(int(year), int(month), 1)


def raw_dir(source: str, release: str) -> Path:
    """Immutable snapshot directory, e.g. data/raw/zillow/2026-09."""
    return RAW_DIR / source / validate_release(release)


def processed_dir(release: str) -> Path:
    """Derived outputs for a release, e.g. data/processed/2026-09. Safe to rebuild."""
    return PROCESSED_DIR / validate_release(release)


# Forecast subjects: Zillow metros (ZHVI), national FRED macro series, and FRED
# metro unemployment rates (keyed by Zillow RegionID).
DATASETS: tuple[str, ...] = ("zillow", "fred", "fred_metro")


def runs_dir(release: str, dataset: str = "zillow") -> Path:
    """Persisted backtest runs for a release; Zillow keeps the original `runs/` path."""
    return processed_dir(release) / ("runs" if dataset == "zillow" else f"runs_{dataset}")


def forecasts_table(dataset: str = "zillow") -> str:
    """Processed table name holding a dataset's forecasts."""
    return "forecasts" if dataset == "zillow" else f"forecasts_{dataset}"
