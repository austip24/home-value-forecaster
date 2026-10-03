"""Export the files the web app reads into web/data/, for deploys without a database.

The bundle is derived and replaced on every export: it copies from data/raw and
data/processed but never writes to them. Only what the dashboard reads is included
(no backtest predictions, features, or raw metro files), keeping it to a few MB.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

from forecaster import config
from forecaster.config import DATASETS, REPO_ROOT, forecasts_table, processed_dir
from forecaster.runs import git_sha, latest_run
from forecaster.snapshots import find_snapshot
from forecaster.sources import FRED_SOURCES, ZHVI

log = logging.getLogger(__name__)

DEFAULT_DEST = REPO_ROOT / "web" / "data"

# Processed tables the web app reads besides forecasts (lib/forecast-data.ts).
OPTIONAL_TABLES = ("macro", "unemployment_metro", "unemployment_metro_crosswalk")


def export_web(release: str, dest: Path = DEFAULT_DEST) -> Path:
    """Write the web bundle for `release` to `dest`; returns the manifest path."""
    files: list[tuple[Path, Path]] = []  # (source, path relative to dest)

    zhvi = find_snapshot("zillow", release, ZHVI.stem)
    if zhvi is None:
        raise FileNotFoundError(f"no ZHVI snapshot for {release}; run ingest first")
    files.append((zhvi, Path("raw", "zillow", release, zhvi.name)))

    for source in FRED_SOURCES:
        path = find_snapshot("fred", release, source.stem)
        if path is None:
            log.warning("no FRED %s snapshot for %s; omitted", source.metric, release)
            continue
        files.append((path, Path("raw", "fred", release, path.name)))

    processed = processed_dir(release)
    for dataset in DATASETS:
        name = f"{forecasts_table(dataset)}.parquet"
        if (processed / name).exists():
            files.append((processed / name, Path("processed", release, name)))
        elif dataset == "zillow":
            raise FileNotFoundError(f"no forecasts for {release}; run `forecaster forecast`")
        else:
            log.warning("no %s forecasts for %s; omitted", dataset, release)

        run = latest_run(release, dataset)
        if run is None:
            log.warning("no %s backtest run for %s; omitted", dataset, release)
            continue
        rel = run.path.relative_to(processed)
        for part in ("run.json", "metrics.parquet"):
            files.append((run.path / part, Path("processed", release, rel, part)))

    for table in OPTIONAL_TABLES:
        path = processed / f"{table}.parquet"
        if path.exists():
            files.append((path, Path("processed", release, path.name)))
        else:
            log.warning("no %s table for %s; omitted", table, release)

    _replace_bundle(dest, files)
    sizes = sorted((rel.as_posix(), (dest / rel).stat().st_size) for _, rel in files)
    manifest = {
        "release": release,
        "git_sha": git_sha(),
        "exported_at": datetime.now(UTC).isoformat(),
        "files": [{"path": path, "bytes": size} for path, size in sizes],
    }
    manifest_path = dest / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    total = sum(size for _, size in sizes)
    log.info("exported %d files (%.1f MB) to %s", len(files), total / 1e6, dest)
    return manifest_path


def _replace_bundle(dest: Path, files: list[tuple[Path, Path]]) -> None:
    """Swap in the new bundle; refuses to touch the pipeline's own data folders."""
    resolved = dest.resolve()
    for protected in (config.RAW_DIR.resolve(), config.PROCESSED_DIR.resolve()):
        if resolved.is_relative_to(protected) or protected.is_relative_to(resolved):
            raise ValueError(f"refusing to export over pipeline data at {dest}")
    for sub in ("raw", "processed"):
        shutil.rmtree(dest / sub, ignore_errors=True)
    for source, rel in files:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
