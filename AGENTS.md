<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.

## Project overview

A housing market forecaster that predicts metro-level home values using Zillow Research data plus macroeconomic indicators, and presents forecasts, backtests, and market signals in a web dashboard.

- **Target:** Zillow Home Value Index (ZHVI), All Homes (SFR + Condo/Co-op), mid-tier, smoothed & seasonally adjusted, metro level.
- **Horizons:** 1, 3, and 12 months ahead.
- **Benchmark:** Zillow's own Home Value Forecast (ZHVF) at the same horizons. Every model must be compared against it and against simple baselines.
- **Architecture:** batch forecasting. A Python pipeline runs monthly after Zillow's release (~16th of each month), writes forecasts to the database, and the Next.js app reads them. There is no real-time model inference.

## Repository layout

```
.
├── web/                    # Next.js (App Router) + shadcn/ui frontend
│   ├── src/
│   │   ├── app/            # Routes, layouts, server components
│   │   ├── components/
│   │   │   ├── ui/         # shadcn primitives (generated, do not hand-edit)
│   │   │   ├── charts/     # Forecast, history, and signal charts
│   │   │   └── ...         # Other app components, grouped by feature
│   │   ├── lib/
│   │   │   ├── db.ts       # Postgres client (server-only)
│   │   │   ├── queries.ts  # Typed read queries used by server components
│   │   │   ├── types.ts    # Types mirroring the database contract
│   │   │   └── utils.ts    # shadcn `cn` helper and shared utils
│   │   └── hooks/          # Client-side React hooks
│   ├── public/             # Static assets
│   ├── components.json     # shadcn config
│   ├── next.config.ts
│   ├── tsconfig.json       # `@/*` alias maps to `./src/*`
│   ├── postcss.config.mjs
│   ├── eslint.config.mjs
│   ├── package.json
│   └── .env.example
├── forecaster/             # Python forecasting pipeline
│   ├── src/forecaster/
│   │   ├── ingest/         # Download + snapshot raw data (Zillow, FRED)
│   │   ├── transform/      # Clean, reshape wide→long, build features
│   │   ├── models/         # Baselines, statistical, ML models
│   │   ├── backtest/       # Rolling-origin evaluation
│   │   └── publish/        # Write forecasts + metrics to the database
│   ├── tests/
│   └── pyproject.toml
├── data/                   # Local data (gitignored except README)
│   ├── raw/zillow/YYYY-MM/ # Immutable monthly snapshots
│   ├── raw/fred/YYYY-MM/
│   └── processed/
└── AGENTS.md
```

## Setup and commands

### Frontend (`web/`)

- Package manager: **pnpm**
- `pnpm install` — install dependencies
- `pnpm dev` — start dev server
- `pnpm build` — production build (must pass before committing)
- `pnpm lint` — ESLint
- `pnpm typecheck` — `tsc --noEmit`
- Add shadcn components with `pnpm dlx shadcn@latest add <component>`; do not hand-write files in `src/components/ui`.

### Forecaster (`forecaster/`)

- Package/env manager: **Poetry** (2.x), Python 3.12+. The venv lives in `forecaster/.venv` (see `poetry.toml`).
- `poetry install` — install dependencies
- `poetry run forecaster ingest --release YYYY-MM` — download and snapshot raw data
- `poetry run forecaster build-features --release YYYY-MM`
- `poetry run forecaster backtest --release YYYY-MM` — `--origins N`, `-m <model>`, `--dataset zillow|fred|fred_metro|all` to narrow
- `poetry run forecaster forecast --release YYYY-MM` — Zillow metros, national FRED series, and metro unemployment (`--dataset` to narrow)
- `poetry run forecaster publish --release YYYY-MM` — applies pending migrations first
- `poetry run forecaster migrate` — apply migrations only
- `poetry run forecaster export-web --release YYYY-MM` — copy the files the web app reads into `web/data/` (the deploy bundle; see README "Deploying to Vercel"). `web/data/` is generated: re-export rather than hand-edit it.
- `poetry run pytest` — tests
- `poetry run ruff check . && poetry run ruff format --check .` — lint/format
- `poetry run mypy src` — type check
- Add dependencies with `poetry add <pkg>` (or `poetry add --group dev <pkg>`); commit `poetry.lock`.
- `FORECASTER_N_JOBS` caps worker processes/threads for model fitting (default: all cores).

## Data sources

| Source          | Data                                                                                                      | Geography        | Notes                                              |
| --------------- | --------------------------------------------------------------------------------------------------------- | ---------------- | -------------------------------------------------- |
| Zillow Research | ZHVI (target), ZHVF (benchmark)                                                                           | Metro            | Direct CSV downloads from `files.zillowstatic.com` |
| Zillow Research | Inventory, new listings, newly pending, price cut share, sale-to-list, days to pending, market heat index | Metro            | Prefer **raw** (unsmoothed) versions for features  |
| FRED            | 30-yr mortgage rate, unemployment, CPI                                                                    | National / metro | Use `fredapi`; API key in `FRED_API_KEY`           |

### File naming

Raw files are saved unmodified as `data/raw/<source>/<YYYY-MM>/<metric>_<geo>_<hometype>_<adjustment>.csv`, e.g. `data/raw/zillow/2026-09/zhvi_metro_allhomes_sm_sa.csv`. `YYYY-MM` is the **release month** (when downloaded), not the last data month in the file.

## Critical data rules

These rules exist to keep backtests honest. Violating them silently invalidates results.

1. **Raw snapshots are immutable.** Never overwrite or edit files in `data/raw/`. Zillow revises history every release and publishes no point-in-time archive, so our snapshots are the only record of what was known when.
2. **No lookahead.** When training or forecasting as of date _T_, only use data published on or before _T_. Zillow sales metrics for month _M_ publish around the 16th of _M+1_; account for each series' publication lag.
3. **Backtest on vintage data.** Rolling-origin backtests should use the snapshot that existed at each origin when one is available. When only current-vintage data exists, label results as such.
4. **Raw over smoothed for features.** Smoothed series average over multiple months and can leak future information. The target (smoothed ZHVI) is the exception, since we are explicitly forecasting it.
5. **Reshape consistently.** Zillow CSVs are wide (one column per month). Convert to long format with columns `region_id, region_name, state, date, value` before anything else. `region_id` (Zillow's `RegionID`) is the join key, never the name.
6. **Handle missing data explicitly.** Many smaller metros have short or gappy histories. Exclude series with fewer than 36 months of history from training and log what was excluded.

## Modeling

Build in this order; each stage must beat the previous on backtests to justify its complexity.

1. **Baselines:** naive (last value), seasonal naive, random walk with drift.
2. **Statistical:** AutoETS and AutoARIMA per metro via `statsforecast`.
3. **Global ML model:** LightGBM trained across all metros with the direct strategy (one model per horizon, target = log growth origin → origin + h), using lagged target, lagged market features, and macro features. Features come from `transform/features.py`, which applies each series' publication lag from `sources.py`; direct (not recursive) forecasting means exogenous features never need to be forecast.
4. **Benchmark:** Zillow ZHVF, converted from growth rates to levels using the ZHVI value at the forecast origin.

Optional later: ensembles, prediction intervals via conformal prediction, hierarchical reconciliation (metro → national).

### Evaluation

- Rolling-origin backtest, monthly origins, at least 24 origins.
- Metrics: **MASE** (primary), MAPE, and directional accuracy (did we predict up vs. down correctly), reported per horizon.
- Report results overall, by metro size tier, and for a fixed showcase set including Phoenix-Mesa-Chandler, AZ.
- Persist every backtest run with its config, data release, git SHA, and metrics. Never report a number that can't be reproduced.

## Database contract

Postgres is the handoff between the forecaster and the web app. The forecaster writes; the web app only reads.

- `regions(region_id PK, region_name, state, size_rank)`
- `observations(region_id, date, metric, value, release)` — historical values
- `forecasts(region_id, origin_date, target_date, horizon, model, value, lower, upper, target, release)`; `target` is what is forecast (`zhvi`, `mortgage_rate`, `unemployment`, `cpi`)
- `backtest_metrics(run_id, model, horizon, metric, value, segment)`
- `runs(run_id PK, release, git_sha, config JSONB, created_at)`

Schema changes go through migrations in `forecaster/migrations/` and must be reflected in `web/src/lib/types.ts` in the same change.

## Frontend conventions

- Next.js App Router, TypeScript strict mode. No `any`.
- Data fetching happens in **server components** via functions in `web/src/lib/queries.ts`. Client components receive data as props and handle interactivity only.
- Use shadcn/ui primitives and shadcn charts (Recharts) for all visualizations. Keep chart styling consistent via the theme's CSS variables.
- Core views:
  - **Overview:** national trend, biggest projected gainers/decliners.
  - **Metro detail:** history + forecast with intervals, our model vs. ZHVF, market signals (inventory, price cuts, days to pending).
  - **Model performance:** backtest metrics by model and horizon.
- Every forecast shown in the UI displays its model, origin date, and data release.
- Accessibility: charts need text alternatives (summary stats or a data table toggle).

## Code style

- **Python:** ruff for lint/format, type hints everywhere, mypy clean. Prefer `polars` for transforms; use pandas only where a library requires it. Pure functions in `transform/` and `models/`; I/O lives in `ingest/` and `publish/`.
- **TypeScript:** ESLint + Prettier defaults. Named exports. Co-locate component-specific helpers.
- Keep functions small and testable. No notebooks in `src/`; exploratory notebooks go in `forecaster/notebooks/` and must not be imported.

## Testing

- Unit tests for every transform and feature function, using small fixture CSVs in `forecaster/tests/fixtures/`.
- A dedicated **leakage test**: for a given origin date, assert that no feature row uses data published after it.
- A smoke test that runs the full pipeline end to end on a tiny fixture dataset.
- Frontend: typecheck and build must pass; add component tests for any non-trivial client logic.

## Secrets and config

- `FRED_API_KEY`, `DATABASE_URL` live in `.env` files, never committed. Provide `.env.example` in both `web/` and `forecaster/`.
- Respect source terms: attribute Zillow and Redfin data in the UI footer and README.

## Agent guidelines

- Run the relevant lint, typecheck, and tests before declaring a task done.
- Do not modify `data/raw/` or delete snapshots.
- Do not add new dependencies without stating why in the change description.
- When a modeling change affects results, rerun the backtest and include the before/after metrics.
- When unsure whether something introduces lookahead bias, assume it does and ask.
