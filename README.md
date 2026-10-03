# Home Value Forecaster

Forecasts typical home values for U.S. metro areas 1, 3, and 12 months ahead, and shows
them in a web dashboard next to Zillow's own forecast.

- **Target:** Zillow Home Value Index (ZHVI), all homes, mid-tier, smoothed and seasonally
  adjusted, for ~900 metros plus the U.S.
- **Models:** simple baselines, per-metro statistical models (AutoETS, AutoARIMA), and a
  global LightGBM model, all scored against Zillow's published forecast (ZHVF).
- **Macro outlook:** the same models and backtests also forecast the national 30-year
  mortgage rate, unemployment rate, and CPI from FRED, plus unemployment rates for
  ~325 metros.
- **Honest evaluation:** a 24-origin rolling backtest, with explicit publication lags so
  no model sees data before it was released.

## How it works

```
 Zillow Research ─┐
                  ├─► forecaster/ (Python, monthly batch) ─► data/processed/ ─► web/ (Next.js)
 FRED (macro) ────┘        ingest → features → backtest              └─► Postgres (optional)
                           → forecast → publish
```

1. Zillow publishes new data around the **16th of each month**. That month is a *release*,
   e.g. `2026-09`, holding data through August.
2. The **forecaster** snapshots the raw files, builds features, backtests every model,
   and writes forecasts.
3. The **web app** reads those outputs and shows history, forecasts with 80% intervals,
   quick insights, projected movers, and backtest results.

There's no live model inference: the dashboard only shows what the last pipeline run
produced.

## Repository layout

| Path | What's there |
| --- | --- |
| [`forecaster/`](forecaster/) | Python pipeline (Poetry). Models, backtests, publishing. See [forecaster/README.md](forecaster/README.md). |
| [`web/`](web/) | Next.js App Router dashboard with shadcn/ui and Recharts. |
| [`data/`](data/) | Local raw snapshots and processed outputs. Gitignored except the README. |
| [`AGENTS.md`](AGENTS.md) | Conventions, data rules, and commands for contributors and AI agents. |

## Getting started

### Prerequisites

- Python 3.12+ and [Poetry](https://python-poetry.org/) 2.x (`pipx install poetry`)
- Node.js 20.9+ and [pnpm](https://pnpm.io/)
- Optional: a free [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html) for
  macro features (mortgage rate, unemployment, CPI)
- Optional: PostgreSQL, if you want to publish to a database

### 1. Run the forecaster

```bash
cd forecaster
cp .env.example .env        # add FRED_API_KEY (and DATABASE_URL if publishing)
poetry install

poetry run forecaster ingest         --release 2026-09
poetry run forecaster build-features --release 2026-09
poetry run forecaster backtest       --release 2026-09   # ~10 min on a multi-core machine
poetry run forecaster forecast       --release 2026-09
```

Use the current Zillow release for `--release`. `ingest` refuses to snapshot files that
don't belong to the release you name, because Zillow doesn't keep an archive.

### 2. Run the dashboard

```bash
cd forecaster
poetry run forecaster export-web --release 2026-09   # copy what the app reads into web/data/

cd ../web
pnpm install
pnpm dev                    # http://localhost:3000
```

The dashboard reads a ~5 MB bundle in `web/data/` (listed in `web/data/MANIFEST.json`),
so it needs no database. To view live pipeline output without exporting, set
`RAW_DATA_DIR=../data/raw` and `PROCESSED_DATA_DIR=../data/processed` in `web/.env.local`
(see [web/.env.example](web/.env.example)).

### 3. (Optional) Publish to Postgres

```bash
cd forecaster
poetry run forecaster publish --release 2026-09   # applies migrations, then writes
```

Postgres is the intended handoff between the two apps. The schema lives in
[`forecaster/migrations/`](forecaster/migrations/), and the dashboard's TypeScript types
mirror it in [`web/src/lib/types.ts`](web/src/lib/types.ts).

## Deploying to Vercel

The deployed app needs no database: it serves the `web/data/` bundle committed to Git,
which `next.config.ts` ships with the page's server function. The forecaster runs on
your machine, and its API keys never reach Vercel.

### First deploy

1. **Commit and push to GitHub.** Create an empty GitHub repository, then:
   ```bash
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
   Make sure `web/data/` is included (run `export-web` first if it's empty).
2. **Import the project.** On [vercel.com](https://vercel.com), choose
   **Add New… → Project**, connect GitHub if prompted, and **Import** the repository.
3. **Configure the project** on the import screen:
   - **Root Directory:** click **Edit** and choose `web`.
   - **Framework Preset:** Next.js (detected automatically).
   - **Build and Output Settings:** leave the defaults. pnpm is detected from
     `pnpm-lock.yaml`.
   - **Environment Variables:** add `ENABLE_EXPERIMENTAL_COREPACK` = `1`, so Vercel
     uses the pnpm version pinned in `web/package.json` (`packageManager`). No other
     variables are needed.
4. Click **Deploy**. When it finishes, open the URL and check a Zillow metro, a FRED
   series, and a FRED metro.
5. **Settings → General → Node.js Version:** confirm it's 22.x (Next.js 16 needs 20.9 or
   newer).

### Monthly update

After Zillow's release (~16th of the month):

```bash
cd forecaster
poetry run forecaster ingest         --release 2026-10
poetry run forecaster build-features --release 2026-10
poetry run forecaster backtest       --release 2026-10
poetry run forecaster forecast       --release 2026-10
poetry run forecaster export-web     --release 2026-10   # replaces web/data/

cd ..
git add web/data
git commit -m "data: 2026-10 release"
git push                     # Vercel deploys main automatically
```

Pushes to other branches get their own preview URLs, which is a safe way to check a new
release before merging. Each release adds about 5 MB to Git history (mostly the ZHVI
CSV); move `web/data` to Git LFS if that ever matters.

## Models

| Model | Kind | In one line |
| --- | --- | --- |
| Naive | Baseline | Value stays where it is today |
| Seasonal naive | Baseline | Same as 12 months ago |
| Random walk + drift | Baseline | Continues the long-run average growth rate |
| AutoETS | Statistical | Exponential smoothing of level and trend, fit per metro |
| AutoARIMA | Statistical | Predicts changes from recent changes and errors, fit per metro |
| LightGBM | Global ML | One model across all metros using momentum, market, and macro features |
| Zillow (ZHVF) | Benchmark | Zillow's published forecast, converted to dollar values |

Each stage has to beat the one before it in the backtest to earn its place. The dashboard
leads with the model that has the lowest average backtest error (MASE) across horizons,
chosen separately for metros and for FRED series.

## Data integrity

Backtests are only useful if they're honest, so the pipeline enforces a few rules (full
list in [AGENTS.md](AGENTS.md)):

- **Raw snapshots are immutable.** Zillow revises history every month, so the monthly
  snapshots are the only record of what was known when.
- **No lookahead.** Every feature respects its source's publication lag, and a dedicated
  leakage test checks this.
- **Vintage labelling.** When a backtest uses today's revised data instead of archived
  snapshots, the run says so, and the dashboard shows it.
- **Reproducible runs.** Every backtest saves its config, data release, git commit, and
  metrics.

## Development

```bash
# forecaster
cd forecaster
poetry run pytest
poetry run ruff check . && poetry run ruff format --check .
poetry run mypy src

# web
cd web
pnpm typecheck && pnpm lint && pnpm build
```

Add shadcn/ui components with `pnpm dlx shadcn@latest add <component>` rather than writing
files in `web/src/components/ui/` by hand.

## Data sources and attribution

- Home values, forecasts, and market metrics:
  [Zillow Research](https://www.zillow.com/research/data/). Zillow Home Value Index
  (ZHVI) and Zillow Home Value Forecast (ZHVF) © Zillow, Inc.
- Mortgage rates, unemployment, and CPI: [FRED](https://fred.stlouisfed.org/), Federal
  Reserve Bank of St. Louis.
- Redfin Data Center appears in the dashboard as a planned provider; no Redfin data is
  used yet. When it is, attribute it as
  [Redfin](https://www.redfin.com/news/data-center/), a national real estate brokerage.

Forecasts are statistical estimates, not financial advice.
