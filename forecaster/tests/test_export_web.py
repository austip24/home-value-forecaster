"""The web bundle holds exactly what the dashboard reads, and nothing heavier."""

import json
from pathlib import Path

import pytest

from forecaster import backtest, config, models, transform
from forecaster.backtest import BacktestConfig
from forecaster.publish.web_bundle import export_web
from tests.conftest import RELEASE


def _run_pipeline() -> None:
    transform.run(RELEASE)
    for dataset in config.DATASETS:
        backtest.run(RELEASE, BacktestConfig(n_origins=2), dataset)
        models.run(RELEASE, dataset)


def test_export_web_bundle(data_root: Path) -> None:
    _run_pipeline()
    dest = data_root / "web-data"
    manifest_path = export_web(RELEASE, dest)

    manifest = json.loads(manifest_path.read_text())
    paths = {f["path"] for f in manifest["files"]}
    assert manifest["release"] == RELEASE

    processed = f"processed/{RELEASE}"
    assert f"raw/zillow/{RELEASE}/zhvi_metro_allhomes_sm_sa.csv" in paths
    assert f"raw/fred/{RELEASE}/mortgage30_national_na_nsa.csv" in paths
    for table in ("forecasts", "forecasts_fred", "forecasts_fred_metro", "macro"):
        assert f"{processed}/{table}.parquet" in paths
    for runs in ("runs", "runs_fred", "runs_fred_metro"):
        assert any(
            p.startswith(f"{processed}/{runs}/") and p.endswith("metrics.parquet") for p in paths
        )

    # Heavy or unused files stay out of the bundle.
    assert not any(p.endswith(("predictions.parquet", "features.parquet")) for p in paths)
    assert not any("unrate_metro" in p for p in paths)  # raw metro family

    # The manifest matches what's on disk.
    on_disk = {p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()} - {
        "MANIFEST.json"
    }
    assert on_disk == paths


def test_export_replaces_previous_bundle(data_root: Path) -> None:
    _run_pipeline()
    dest = data_root / "web-data"
    stale = dest / "processed" / "2000-01" / "forecasts.parquet"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"old")
    export_web(RELEASE, dest)
    assert not stale.exists()


def test_export_refuses_pipeline_data_dirs(data_root: Path) -> None:
    _run_pipeline()
    for dest in (config.RAW_DIR, config.PROCESSED_DIR / RELEASE, config.RAW_DIR.parent):
        with pytest.raises(ValueError, match="refusing"):
            export_web(RELEASE, dest)
