from typer.testing import CliRunner

from forecaster.cli import app

runner = CliRunner()


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ["ingest", "build-features", "backtest", "forecast", "publish"]:
        assert cmd in result.output


def test_rejects_bad_release() -> None:
    result = runner.invoke(app, ["ingest", "--release", "2026-13"])
    assert result.exit_code != 0
