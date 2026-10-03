"""Locate immutable raw snapshots on disk. Read-only helpers."""

from __future__ import annotations

from pathlib import Path

from forecaster import config
from forecaster.config import raw_dir, validate_release


def find_snapshot(source: str, release: str, stem: str) -> Path | None:
    """The snapshot file for `stem` in a release folder, tolerating suffixes after the stem."""
    folder = raw_dir(source, release)
    if not folder.is_dir():
        return None
    matches = sorted(folder.glob(f"{stem}*.csv"))
    return matches[0] if matches else None


def list_releases(source: str) -> list[str]:
    """Release folders present for a source, oldest first."""
    folder = config.RAW_DIR / source
    if not folder.is_dir():
        return []
    releases = []
    for child in folder.iterdir():
        try:
            releases.append(validate_release(child.name))
        except ValueError:
            continue
    return sorted(releases)
