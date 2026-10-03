import pytest

from forecaster.config import raw_dir, validate_release


def test_validate_release_accepts_yyyy_mm() -> None:
    assert validate_release("2026-09") == "2026-09"


@pytest.mark.parametrize("bad", ["2026-9", "2026-13", "26-09", "2026/09", ""])
def test_validate_release_rejects_bad_values(bad: str) -> None:
    with pytest.raises(ValueError):
        validate_release(bad)


def test_raw_dir_layout() -> None:
    path = raw_dir("zillow", "2026-09")
    assert path.parts[-3:] == ("raw", "zillow", "2026-09")
