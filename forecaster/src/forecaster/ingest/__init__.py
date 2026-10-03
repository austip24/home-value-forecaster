"""Download Zillow and FRED data into data/raw/<source>/<release>/ (never overwrite)."""

from __future__ import annotations

import csv
import io
import logging
import os
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import pandas as pd

from forecaster.config import FRED_API_KEY, raw_dir, release_month
from forecaster.snapshots import find_snapshot
from forecaster.sources import (
    FRED_METRO_UNEMPLOYMENT,
    FRED_SOURCES,
    ZHVI,
    ZILLOW_SOURCES,
    FredMetroSource,
    FredSource,
)

log = logging.getLogger(__name__)
# httpx logs full request URLs at INFO, which would put the FRED API key in logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

FRED_API_URL = "https://api.stlouisfed.org/fred"
# FRED allows 120 requests per minute per key; stay comfortably under it.
FRED_REQUEST_INTERVAL = 0.6

# Zillow publishes around the 16th; FRED values are pulled as known on this day.
RELEASE_DAY = 16


def expected_last_data_month(release: str) -> date:
    """Month-end date of the last ZHVI month contained in a release."""
    return release_month(release) - timedelta(days=1)


def last_date_column(header: list[str]) -> date | None:
    """Latest YYYY-MM-DD column in a wide Zillow header."""
    dates = []
    for col in header:
        try:
            dates.append(date.fromisoformat(col))
        except ValueError:
            continue
    return max(dates) if dates else None


def _write_atomic(dest: Path, content: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".tmp")
    with os.fdopen(fd, "wb") as f:
        f.write(content)
    if dest.exists():
        os.unlink(tmp)
        raise FileExistsError(f"refusing to overwrite snapshot {dest}")
    os.replace(tmp, dest)


def _fetch(client: httpx.Client, url: str) -> bytes:
    response = client.get(url, follow_redirects=True, timeout=120)
    response.raise_for_status()
    return response.content


def verify_zillow_release(client: httpx.Client, release: str) -> bytes:
    """Download ZHVI and confirm Zillow's live files are the requested release.

    Zillow keeps no archive, so the live files are only valid for the current release.
    Returns the ZHVI bytes so the caller can snapshot them.
    """
    content = _fetch(client, ZHVI.url)
    header = next(csv.reader(io.StringIO(content[:65536].decode("utf-8", errors="replace"))))
    last = last_date_column(header)
    expected = expected_last_data_month(release)
    if last != expected:
        raise RuntimeError(
            f"Zillow's live ZHVI ends {last}, but release {release} should end {expected}. "
            "Live files can only be snapshotted under the release they belong to."
        )
    return content


def ingest_zillow(release: str, client: httpx.Client) -> list[Path]:
    zhvi_bytes = verify_zillow_release(client, release)
    folder = raw_dir("zillow", release)
    written: list[Path] = []
    for source in ZILLOW_SOURCES:
        if find_snapshot("zillow", release, source.stem):
            log.info("zillow %s: snapshot exists, skipping", source.metric)
            continue
        try:
            content = zhvi_bytes if source is ZHVI else _fetch(client, source.url)
        except httpx.HTTPError as e:
            if source.required:
                raise
            log.warning("zillow %s: download failed (%s), skipping", source.metric, e)
            continue
        dest = folder / f"{source.stem}.csv"
        _write_atomic(dest, content)
        written.append(dest)
        log.info("zillow %s: wrote %s", source.metric, dest)
    return written


def fred_as_of(release: str, today: date | None = None) -> date:
    """The real-time date for FRED values: release day, or today if that is later."""
    release_day = release_month(release).replace(day=RELEASE_DAY)
    return min(release_day, today or date.today())


def ingest_fred(release: str, api_key: str = FRED_API_KEY) -> list[Path]:
    if not api_key:
        log.warning("FRED_API_KEY not set; skipping FRED ingest")
        return []
    from fredapi import Fred

    fred = Fred(api_key=api_key)
    as_of = fred_as_of(release).isoformat()
    folder = raw_dir("fred", release)
    written: list[Path] = []
    for source in FRED_SOURCES:
        if find_snapshot("fred", release, source.stem):
            log.info("fred %s: snapshot exists, skipping", source.metric)
            continue
        written.append(_ingest_fred_series(fred, source, as_of, folder))
    return written


def _ingest_fred_series(fred: object, source: FredSource, as_of: str, folder: Path) -> Path:
    # ALFRED real-time window: values exactly as they were known on `as_of`.
    series = fred.get_series(  # type: ignore[attr-defined]
        source.series_id, realtime_start=as_of, realtime_end=as_of
    )
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["date", "value", "realtime_as_of"])
    for ts, value in series.items():
        writer.writerow([ts.date().isoformat(), "" if value != value else value, as_of])
    dest = folder / f"{source.stem}.csv"
    _write_atomic(dest, buf.getvalue().encode())
    log.info("fred %s: wrote %s (as of %s)", source.metric, dest, as_of)
    return dest


def list_fred_family(
    client: httpx.Client, source: FredMetroSource, api_key: str, as_of: date
) -> list[dict[str, str]]:
    """Series in a tag family that are still published (data within a year of as_of)."""
    found: list[dict[str, str]] = []
    offset = 0
    while True:
        response = client.get(
            f"{FRED_API_URL}/tags/series",
            params={
                "tag_names": source.tag_names,
                "api_key": api_key,
                "file_type": "json",
                "limit": 1000,
                "offset": offset,
            },
            timeout=60,
        )
        response.raise_for_status()
        page = response.json()
        found.extend(page["seriess"])
        offset += 1000
        if offset >= page["count"]:
            break
    current_since = (as_of - timedelta(days=365)).isoformat()
    return sorted(
        (
            {"id": s["id"], "title": s["title"]}
            for s in found
            if s["title"].startswith(source.title_prefix) and s["observation_end"] >= current_since
        ),
        key=lambda s: s["id"],
    )


def ingest_fred_metro(
    release: str, source: FredMetroSource = FRED_METRO_UNEMPLOYMENT, api_key: str = FRED_API_KEY
) -> Path | None:
    """Snapshot every metro series in a family, as known on release day, to one CSV."""
    if not api_key:
        log.warning("FRED_API_KEY not set; skipping FRED metro ingest")
        return None
    if find_snapshot("fred", release, source.stem):
        log.info("fred %s: snapshot exists, skipping", source.metric)
        return None
    from fredapi import Fred

    as_of = fred_as_of(release)
    with httpx.Client(headers={"User-Agent": "home-value-forecaster/0.1"}) as client:
        family = list_fred_family(client, source, api_key, as_of)
    log.info("fred %s: %d current series; fetching as of %s", source.metric, len(family), as_of)

    fred = Fred(api_key=api_key)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["series_id", "title", "date", "value", "realtime_as_of"])
    skipped = 0
    for i, series in enumerate(family, 1):
        values = _fetch_as_of(fred, series["id"], as_of.isoformat())
        if values is None:
            skipped += 1
            continue
        dates = pd.DatetimeIndex(values.index)
        for ts, value in zip(dates, values.to_numpy(), strict=True):
            if value == value:  # drop NaN
                writer.writerow(
                    [
                        series["id"],
                        series["title"],
                        pd.Timestamp(ts).date().isoformat(),
                        value,
                        as_of,
                    ]
                )
        if i % 50 == 0:
            log.info("fred %s: %d/%d series", source.metric, i, len(family))
        time.sleep(FRED_REQUEST_INTERVAL)

    dest = raw_dir("fred", release) / f"{source.stem}.csv"
    _write_atomic(dest, buf.getvalue().encode())
    log.info(
        "fred %s: wrote %s (%d series, %d without data as of %s)",
        source.metric,
        dest,
        len(family) - skipped,
        skipped,
        as_of,
    )
    return dest


def _fetch_as_of(fred: object, series_id: str, as_of: str) -> pd.Series | None:
    """One series as known on `as_of`; retries once if FRED rate-limits."""
    for attempt in range(2):
        try:
            return fred.get_series(  # type: ignore[attr-defined, no-any-return]
                series_id, realtime_start=as_of, realtime_end=as_of
            )
        except ValueError as e:  # fredapi raises ValueError for API errors
            if attempt == 0 and "Too Many Requests" in str(e):
                time.sleep(30)
                continue
            log.warning("fred %s: no data as of %s (%s)", series_id, as_of, e)
            return None
    return None


def run(release: str) -> None:
    with httpx.Client(headers={"User-Agent": "home-value-forecaster/0.1"}) as client:
        ingest_zillow(release, client)
    ingest_fred(release)
    ingest_fred_metro(release)
