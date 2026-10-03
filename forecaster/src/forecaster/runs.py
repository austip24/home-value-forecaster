"""Persist backtest runs (config, data release, git SHA, predictions, metrics) to disk."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from forecaster.config import REPO_ROOT, runs_dir


@dataclass(frozen=True)
class Run:
    run_id: str
    release: str
    git_sha: str
    config: dict[str, Any]
    created_at: str
    path: Path

    def predictions(self) -> pl.DataFrame:
        return pl.read_parquet(self.path / "predictions.parquet")

    def metrics(self) -> pl.DataFrame:
        return pl.read_parquet(self.path / "metrics.parquet")


def git_sha() -> str:
    """HEAD commit, suffixed with -dirty when the working tree has uncommitted changes."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "forecaster"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{sha}-dirty" if dirty else sha


def save_run(
    release: str,
    config: dict[str, Any],
    predictions: pl.DataFrame,
    metrics: pl.DataFrame,
    dataset: str = "zillow",
) -> Run:
    now = datetime.now(UTC)
    run_id = f"{release}_{now:%Y%m%dT%H%M%SZ}" + ("" if dataset == "zillow" else f"_{dataset}")
    path = runs_dir(release, dataset) / run_id
    path.mkdir(parents=True, exist_ok=False)
    # Round-trip through JSON so the returned Run matches what load_run() reads back.
    config = json.loads(json.dumps(config, default=str))
    run = Run(run_id, release, git_sha(), config, now.isoformat(), path)
    meta = {k: getattr(run, k) for k in ("run_id", "release", "git_sha", "config", "created_at")}
    (path / "run.json").write_text(json.dumps(meta, indent=2))
    predictions.write_parquet(path / "predictions.parquet")
    metrics.write_parquet(path / "metrics.parquet")
    return run


def load_run(path: Path) -> Run:
    meta = json.loads((path / "run.json").read_text())
    return Run(path=path, **meta)


def latest_run(release: str, dataset: str = "zillow") -> Run | None:
    folder = runs_dir(release, dataset)
    if not folder.is_dir():
        return None
    candidates = sorted(p for p in folder.iterdir() if (p / "run.json").exists())
    return load_run(candidates[-1]) if candidates else None
