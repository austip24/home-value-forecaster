# forecaster

Batch pipeline that forecasts metro-level Zillow ZHVI 1, 3, and 12 months ahead and
publishes results to Postgres for the `web/` dashboard. See the root `AGENTS.md` for data
rules and conventions.

## Setup

Requires Python 3.12+ and [Poetry](https://python-poetry.org/) 2.x
(`pipx install poetry`).

```bash
cd forecaster
cp .env.example .env   # add FRED_API_KEY and DATABASE_URL
poetry install
poetry run pytest
```

## Pipeline

Run monthly after Zillow's release (~16th). `--release` is the Zillow release month; its
last ZHVI month is the month before.

```bash
poetry run forecaster ingest         --release 2026-09   # snapshot Zillow + FRED (add-only)
poetry run forecaster build-features --release 2026-09   # wide -> long, features
poetry run forecaster backtest       --release 2026-09   # 24-origin rolling backtest (Zillow + FRED)
poetry run forecaster forecast       --release 2026-09   # forecasts at the latest origin (Zillow + FRED)
poetry run forecaster publish        --release 2026-09   # migrate + write to Postgres
```

`ingest` refuses to snapshot unless Zillow's live files really are the requested
release, because Zillow keeps no archive. FRED values are fetched as they were known on
release day (ALFRED real-time), not as later revised.

## Datasets

The same steps run for three kinds of forecast subject (`--dataset` narrows to one):

- **zillow**: ~900 metros plus the U.S., target ZHVI, benchmarked against ZHVF.
- **fred**: the 30-year mortgage rate, unemployment rate, and CPI, keyed as
  `region_id` 900001–900003 so they reuse the metro pipeline unchanged. They forecast
  from the same origin as Zillow (the month before the release) and have no published
  benchmark. Outputs: `forecasts_fred.parquet` and `runs_fred/`.
- **fred_metro**: metro unemployment rates (BLS via FRED, smoothed seasonally
  adjusted), matched to Zillow metros by principal city and state
  (`transform/crosswalk.py`) and keyed by Zillow RegionID, so size tiers and showcase
  metros match the home-value backtest. Metro data lags about a month, so the origin
  is the latest month in the snapshot. Metros with no current adjusted series on FRED
  (most of New England, Honolulu, North Port, Cleveland OH) are not covered.
  Outputs: `unemployment_metro*.parquet`, `forecasts_fred_metro.parquet`, `runs_fred_metro/`.

Every forecast row carries a `target` (`zhvi`, `mortgage_rate`, `unemployment`,
`cpi`); migration `002_forecast_target.sql` adds it to the `forecasts` primary key.

## Models

| Model            | Kind        | Notes                                                       |
| ---------------- | ----------- | ----------------------------------------------------------- |
| `naive`          | baseline    | Last value                                                  |
| `seasonal_naive` | baseline    | Value 12 months earlier (ZHVI is SA, so this is weak)       |
| `rw_drift`       | baseline    | Random walk with drift, on log ZHVI                         |
| `auto_ets`       | statistical | statsforecast AutoETS per metro, log ZHVI                   |
| `auto_arima`     | statistical | statsforecast AutoARIMA per metro, log ZHVI                 |
| `lightgbm`       | global ML   | One direct model per horizon across all metros              |
| `zhvf`           | benchmark   | Zillow's forecast, growth % converted to levels at origin   |

Intervals are 80%. statsforecast models produce their own intervals; LightGBM uses
split-conformal intervals from the latest backtest's out-of-sample errors, by horizon
and metro size tier.

## Outputs

- `data/processed/<release>/*.parquet`: long-format inputs, features, and `forecasts`.
- `data/processed/<release>/runs/<run_id>/`: each backtest's `run.json` (config, git
  SHA, origins, data vintage), `predictions.parquet`, and `metrics.parquet`.

## Backtest honesty

- Features at origin _t_ only use data whose month plus publication lag is ≤ _t_
  (`sources.py`). `tests/test_leakage.py` asserts this.
- When a raw snapshot exists for a backtest origin, the backtest trains on that vintage.
  Otherwise it uses current-vintage data, and the run's `data_vintage` says so.
- ZHVF can only be scored at origins where we archived its snapshot. The
  `benchmark_matched` segment compares every model with ZHVF on exactly those rows.
