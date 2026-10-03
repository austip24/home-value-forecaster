"""Read raw snapshots from disk without modifying them."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from forecaster.snapshots import find_snapshot
from forecaster.sources import FredMetroSource, FredSource, ZillowSource


def read_wide_csv(path: Path) -> pl.DataFrame:
    """Load a Zillow wide CSV with every column as text; callers cast what they use."""
    return pl.read_csv(path, infer_schema=False)


def read_zillow(source: ZillowSource, release: str) -> pl.DataFrame | None:
    path = find_snapshot("zillow", release, source.stem)
    return read_wide_csv(path) if path else None


def read_fred_family(source: FredMetroSource, release: str) -> pl.DataFrame | None:
    path = find_snapshot("fred", release, source.stem)
    return pl.read_csv(path, infer_schema=False) if path else None


def read_fred(source: FredSource, release: str) -> pl.DataFrame | None:
    path = find_snapshot("fred", release, source.stem)
    return pl.read_csv(path, infer_schema=False) if path else None
