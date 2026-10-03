"""Command-line entry point: `poetry run forecaster <command> --release YYYY-MM`."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from forecaster.config import BACKTEST_ORIGINS, DATASETS, validate_release

app = typer.Typer(help="Housing market forecaster pipeline.", no_args_is_help=True)

ReleaseOpt = typer.Option(..., "--release", "-r", help="Data release month, YYYY-MM.")

DatasetOpt = Annotated[
    str,
    typer.Option(
        "--dataset",
        "-d",
        help=f"Which forecast subjects: {', '.join(DATASETS)}, or all.",
    ),
]


def _datasets(dataset: str) -> tuple[str, ...]:
    if dataset == "all":
        return DATASETS
    if dataset not in DATASETS:
        raise typer.BadParameter(f"dataset must be one of {(*DATASETS, 'all')}")
    return (dataset,)


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _check(release: str) -> str:
    try:
        return validate_release(release)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e


@app.command()
def ingest(release: str = ReleaseOpt) -> None:
    """Download and snapshot raw data (Zillow, FRED)."""
    from forecaster.ingest import run

    run(_check(release))


@app.command("build-features")
def build_features(release: str = ReleaseOpt) -> None:
    """Reshape raw data to long format and build model features."""
    from forecaster.transform import run

    run(_check(release))


@app.command()
def backtest(
    release: str = ReleaseOpt,
    origins: Annotated[int, typer.Option(help="Number of monthly origins.")] = BACKTEST_ORIGINS,
    models: Annotated[
        list[str] | None, typer.Option("--model", "-m", help="Limit to these models.")
    ] = None,
    dataset: DatasetOpt = "all",
) -> None:
    """Run rolling-origin backtests for all models."""
    from forecaster.backtest import BacktestConfig, run
    from forecaster.models import ALL_MODELS

    chosen = tuple(models) if models else ALL_MODELS
    unknown = set(chosen) - set(ALL_MODELS)
    if unknown:
        raise typer.BadParameter(f"unknown model(s) {sorted(unknown)}; choose from {ALL_MODELS}")
    config = BacktestConfig(n_origins=origins, models=chosen)
    for name in _datasets(dataset):
        run(_check(release), config, name)


@app.command()
def forecast(release: str = ReleaseOpt, dataset: DatasetOpt = "all") -> None:
    """Fit models and produce forecasts."""
    from forecaster.models import run

    for name in _datasets(dataset):
        run(_check(release), name)


@app.command()
def publish(release: str = ReleaseOpt) -> None:
    """Write forecasts and backtest metrics to Postgres."""
    from forecaster.publish import run

    run(_check(release))


@app.command("export-web")
def export_web(
    release: str = ReleaseOpt,
    dest: Annotated[Path | None, typer.Option(help="Bundle folder (default: web/data).")] = None,
) -> None:
    """Copy the files the web app reads into web/data/ for deployment."""
    from forecaster.publish.web_bundle import DEFAULT_DEST
    from forecaster.publish.web_bundle import export_web as export

    manifest = export(_check(release), dest or DEFAULT_DEST)
    typer.echo(f"wrote {manifest}")


@app.command()
def migrate() -> None:
    """Apply database migrations."""
    from forecaster.publish import connect
    from forecaster.publish import migrate as apply

    with connect() as conn:
        applied = apply(conn)
    typer.echo(f"applied: {', '.join(applied) or 'nothing (up to date)'}")


if __name__ == "__main__":
    app()
