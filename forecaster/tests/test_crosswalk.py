import polars as pl

from forecaster.transform.crosswalk import match_metros, parse_metro_title

PREFIX = "Unemployment Rate in "


def test_parse_metro_title() -> None:
    assert parse_metro_title(
        "Unemployment Rate in New York-Newark-Jersey City, NY-NJ-PA (MSA)", PREFIX
    ) == (["new york", "newark", "jersey city"], ["NY", "NJ", "PA"])
    # Aliases after "/" are dropped; punctuation is normalised.
    assert parse_metro_title(
        "Unemployment Rate in Louisville/Jefferson County, KY-IN (MSA)", PREFIX
    ) == (["louisville"], ["KY", "IN"])
    assert parse_metro_title("Unemployment Rate in St. Louis, MO-IL (MSA)", PREFIX) == (
        ["st louis"],
        ["MO", "IL"],
    )
    assert parse_metro_title("Labor Force in Abilene, TX (MSA)", PREFIX) is None


def _regions(*names: str) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "region_id": list(range(1, len(names) + 1)),
            "region_name": list(names),
            "region_type": ["msa"] * len(names),
        }
    )


def _series(*titles: str) -> pl.DataFrame:
    return pl.DataFrame({"series_id": [f"S{i}" for i in range(len(titles))], "title": list(titles)})


def test_match_on_principal_city_and_state() -> None:
    series = _series(
        "Unemployment Rate in Albany-Schenectady-Troy, NY (MSA)",
        "Unemployment Rate in Albany, GA (MSA)",
        "Unemployment Rate in New York-Newark-Jersey City, NY-NJ-PA (MSA)",
        "Unemployment Rate in St. Louis, MO-IL (MSA)",
    )
    regions = _regions("Albany, NY", "Albany, GA", "New York, NY", "St. Louis, MO", "Nowhere, ZZ")
    crosswalk = dict(
        match_metros(series, regions, PREFIX).select("region_id", "series_id").iter_rows()
    )
    assert crosswalk == {1: "S0", 2: "S1", 3: "S2", 4: "S3"}


def test_secondary_city_only_when_unambiguous() -> None:
    series = _series(
        "Unemployment Rate in Fayetteville-Springdale-Rogers, AR (MSA)",
        "Unemployment Rate in Springfield, MO (MSA)",
    )
    # "Springdale, AR" is a listed (non-principal) city of exactly one AR metro.
    matched = match_metros(series, _regions("Springdale, AR"), PREFIX)
    assert matched.get_column("series_id").to_list() == ["S0"]


def test_each_series_matches_one_metro() -> None:
    series = _series("Unemployment Rate in Dallas-Fort Worth-Arlington, TX (MSA)")
    matched = match_metros(series, _regions("Dallas, TX", "Fort Worth, TX"), PREFIX)
    assert matched.get_column("region_id").to_list() == [1]


def test_non_metro_regions_are_ignored() -> None:
    regions = pl.DataFrame(
        {"region_id": [1], "region_name": ["United States"], "region_type": ["country"]}
    )
    series = _series("Unemployment Rate in Abilene, TX (MSA)")
    assert match_metros(series, regions, PREFIX).is_empty()


def test_duplicate_families_resolve_to_longest_history() -> None:
    series = pl.DataFrame(
        {
            "series_id": ["DETR826UR", "LASMT261982000000003"],
            "title": ["Unemployment Rate in Detroit-Warren-Dearborn, MI (MSA)"] * 2,
            "n_obs": [440, 20],
        }
    )
    matched = match_metros(series, _regions("Detroit, MI"), PREFIX)
    assert matched.get_column("series_id").to_list() == ["DETR826UR"]
