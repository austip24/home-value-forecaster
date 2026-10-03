"""Match FRED metro series to Zillow metros. Pure functions.

Zillow names a metro by its principal city ("Phoenix, AZ"); FRED titles use the
full OMB name ("Unemployment Rate in Phoenix-Mesa-Chandler, AZ (MSA)"). Neither
carries a shared code, so we match on city + state, which is unambiguous for
metros: a metro's principal city is unique within its state(s).
"""

from __future__ import annotations

import re

import polars as pl

_SUFFIX = re.compile(r"\s*\((MSA|MSAD|CSA|NECTA)\)\s*$")


def _norm(name: str) -> str:
    """Case/punctuation-insensitive city key: 'St. Louis' == 'st louis'."""
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def parse_metro_title(title: str, prefix: str) -> tuple[list[str], list[str]] | None:
    """'Unemployment Rate in Albany-Schenectady-Troy, NY (MSA)' ->
    (['albany', 'schenectady', 'troy'], ['NY']). None if it doesn't parse."""
    if not title.startswith(prefix):
        return None
    name = _SUFFIX.sub("", title[len(prefix) :])
    if ", " not in name:
        return None
    cities_part, states_part = name.rsplit(", ", 1)
    # Cities are "-" separated; some carry an alias after "/" (Louisville/Jefferson County).
    cities = [_norm(c.split("/")[0]) for c in cities_part.split("-")]
    states = [s.strip() for s in states_part.split("-")]
    return cities, states


def match_metros(series: pl.DataFrame, regions: pl.DataFrame, prefix: str) -> pl.DataFrame:
    """One-to-one crosswalk `region_id, series_id, fred_name`.

    series:  series_id, title, and optionally n_obs (one row per FRED series)
    regions: region_id, region_name ("City, ST"), region_type

    A Zillow metro matches a FRED series when its city is the FRED metro's first
    (principal) city and its state is among the metro's states. Failing that, any
    listed city in a shared state counts. FRED sometimes carries one metro in two
    series families (e.g. DETR826UR and LASMT261982000000003); candidates that all
    name the same metro are duplicates, resolved to the longest history. Candidates
    naming different metros are ambiguous and left unmatched.
    """
    has_obs = "n_obs" in series.columns
    parsed = []
    for row in series.unique("series_id").iter_rows(named=True):
        p = parse_metro_title(row["title"], prefix)
        if p is not None:
            name = _SUFFIX.sub("", row["title"][len(prefix) :])
            n_obs = row["n_obs"] if has_obs else 0
            parsed.append((row["series_id"], name, p[0], p[1], n_obs))

    rows: list[tuple[int, str, str]] = []
    used: set[str] = set()
    metros = regions.filter(pl.col("region_type") == "msa")
    for region_id, region_name in metros.select("region_id", "region_name").iter_rows():
        if ", " not in region_name:
            continue
        city, state = region_name.rsplit(", ", 1)
        key = _norm(city)
        primary = [p for p in parsed if p[2][0] == key and state in p[3]]
        candidates = primary or [p for p in parsed if key in p[2] and state in p[3]]
        candidates = [c for c in candidates if c[0] not in used]
        if not candidates or len({c[1] for c in candidates}) > 1:
            continue
        # Same metro in several families: keep the longest history (ties: by id).
        series_id, name, *_ = max(candidates, key=lambda c: (c[4], c[0]))
        rows.append((region_id, series_id, name))
        used.update(c[0] for c in candidates)

    return pl.DataFrame(
        rows,
        schema={"region_id": pl.Int64, "series_id": pl.Utf8, "fred_name": pl.Utf8},
        orient="row",
    )
