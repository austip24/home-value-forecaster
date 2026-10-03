// Server-only reader for the forecaster's outputs in data/processed/.
// Stand-in for Postgres (the forecaster's `publish` step writes the same rows);
// queries.ts is the only caller, so swapping the backend touches one file.

import { readdir, readFile, stat } from "node:fs/promises"
import path from "node:path"

import { asyncBufferFromFile, parquetReadObjects } from "hyparquet"
import { compressors } from "hyparquet-compressors"

import type {
  BacktestMetric,
  DatasetId,
  Forecast,
  MacroPoint,
  RegionOption,
  Run,
  SeriesPoint,
} from "@/lib/types"

// Defaults to the bundle in web/data/ written by `forecaster export-web`, which
// next.config.ts ships with the server function (outputFileTracingIncludes). The
// turbopackIgnore hints stop the bundler from tracing these dynamic paths itself.
const PROCESSED_DATA_DIR =
  process.env.PROCESSED_DATA_DIR ??
  path.join(/*turbopackIgnore: true*/ process.cwd(), "data", "processed")

const processedPath = (...segments: string[]) =>
  path.join(/*turbopackIgnore: true*/ PROCESSED_DATA_DIR, ...segments)

const RELEASE_PATTERN = /^\d{4}-\d{2}$/

export type ForecastDataset = {
  release: string
  originDate: string
  byRegion: Map<number, Forecast[]>
}

// Mirrors forecaster/config.py: Zillow keeps the original names.
const forecastsFile = (dataset: DatasetId) =>
  dataset === "zillow" ? "forecasts.parquet" : `forecasts_${dataset}.parquet`
const runsFolder = (dataset: DatasetId) =>
  dataset === "zillow" ? "runs" : `runs_${dataset}`

/** Newest release folder that has forecasts for a dataset. */
export async function findLatestForecastRelease(
  dataset: DatasetId = "zillow"
): Promise<string | null> {
  const releases = (await safeReaddir(processedPath()))
    .filter((name) => RELEASE_PATTERN.test(name))
    .sort()
    .reverse()
  for (const release of releases) {
    if (await exists(processedPath(release, forecastsFile(dataset))))
      return release
  }
  return null
}

const forecastCache = new Map<
  string,
  { mtimeMs: number; data: Promise<ForecastDataset> }
>()

/** Latest release's forecasts grouped by region, memoized by file path + mtime. */
export async function loadForecasts(
  dataset: DatasetId = "zillow"
): Promise<ForecastDataset | null> {
  const release = await findLatestForecastRelease(dataset)
  if (!release) return null

  const file = processedPath(release, forecastsFile(dataset))
  const { mtimeMs } = await stat(file)
  const cached = forecastCache.get(file)
  if (cached && cached.mtimeMs === mtimeMs) return cached.data

  const data = readParquet(file).then((rows) => groupForecasts(rows, release))
  forecastCache.set(file, { mtimeMs, data })
  return data
}

function groupForecasts(
  rows: Record<string, unknown>[],
  release: string
): ForecastDataset {
  const byRegion = new Map<number, Forecast[]>()
  let originDate = ""
  for (const row of rows) {
    const forecast: Forecast = {
      region_id: toNumber(row.region_id),
      origin_date: toIsoDate(row.origin_date),
      target_date: toIsoDate(row.target_date),
      horizon: toNumber(row.horizon),
      model: String(row.model),
      value: toNumber(row.value),
      lower: toNullableNumber(row.lower),
      upper: toNullableNumber(row.upper),
      target: String(row.target ?? "zhvi"),
      release: String(row.release ?? release),
    }
    if (forecast.origin_date > originDate) originDate = forecast.origin_date
    const list = byRegion.get(forecast.region_id)
    if (list) list.push(forecast)
    else byRegion.set(forecast.region_id, [forecast])
  }
  return { release, originDate, byRegion }
}

const macroCache = new Map<
  string,
  { mtimeMs: number; data: Promise<MacroPoint[]> }
>()

/** Monthly national macro series (FRED) the forecaster used for a release. */
export async function loadMacro(release: string): Promise<MacroPoint[]> {
  const file = processedPath(release, "macro.parquet")
  if (!(await exists(file))) return []

  const { mtimeMs } = await stat(file)
  const cached = macroCache.get(file)
  if (cached && cached.mtimeMs === mtimeMs) return cached.data

  const data = readParquet(file).then((rows) =>
    rows.map((row) => ({
      date: toIsoDate(row.date),
      metric: String(row.metric),
      value: toNumber(row.value),
    }))
  )
  macroCache.set(file, { mtimeMs, data })
  return data
}

export type MetroUnemployment = {
  release: string
  /** Monthly rate by Zillow RegionID. */
  series: Map<number, SeriesPoint[]>
  /** Matched metros, largest first, with the FRED series behind each. */
  metros: {
    region: RegionOption
    seriesId: string
    fredName: string
  }[]
}

const metroCache = new Map<
  string,
  { mtimeMs: number; data: Promise<MetroUnemployment> }
>()

/**
 * FRED metro unemployment rates the forecaster matched to Zillow metros
 * (unemployment_metro.parquet + its crosswalk), from the newest release.
 */
export async function loadMetroUnemployment(): Promise<MetroUnemployment | null> {
  const releases = (await safeReaddir(processedPath()))
    .filter((name) => RELEASE_PATTERN.test(name))
    .sort()
    .reverse()
  for (const release of releases) {
    const file = processedPath(release, "unemployment_metro.parquet")
    const crosswalkFile = processedPath(
      release,
      "unemployment_metro_crosswalk.parquet"
    )
    if (!(await exists(file)) || !(await exists(crosswalkFile))) continue

    const { mtimeMs } = await stat(file)
    const cached = metroCache.get(file)
    if (cached && cached.mtimeMs === mtimeMs) return cached.data

    const data = Promise.all([
      readParquet(file),
      readParquet(crosswalkFile),
    ]).then(([rows, crosswalk]) => {
      const series = new Map<number, SeriesPoint[]>()
      for (const row of rows) {
        const id = toNumber(row.region_id)
        const point = { date: toIsoDate(row.date), value: toNumber(row.value) }
        const list = series.get(id)
        if (list) list.push(point)
        else series.set(id, [point])
      }
      for (const list of series.values()) {
        list.sort((a, b) => a.date.localeCompare(b.date))
      }
      const metros = crosswalk.map((row) => ({
        region: {
          region_id: toNumber(row.region_id),
          region_name: String(row.region_name),
          state: row.state == null ? null : String(row.state),
          size_rank: toNullableNumber(row.size_rank),
          region_type: "msa",
        },
        seriesId: String(row.series_id),
        fredName: String(row.fred_name),
      }))
      metros.sort(
        (a, b) =>
          (a.region.size_rank ?? Infinity) - (b.region.size_rank ?? Infinity)
      )
      return { release, series, metros }
    })
    metroCache.set(file, { mtimeMs, data })
    return data
  }
  return null
}

const runCache = new Map<
  string,
  { mtimeMs: number; data: Promise<{ run: Run; metrics: BacktestMetric[] }> }
>()

/** Most recent backtest run for a release (run ids sort chronologically). */
export async function loadLatestRun(
  release: string,
  dataset: DatasetId = "zillow"
): Promise<{ run: Run; metrics: BacktestMetric[] } | null> {
  const runsDir = processedPath(release, runsFolder(dataset))
  const runIds = (await safeReaddir(runsDir)).sort().reverse()
  for (const runId of runIds) {
    const metaFile = path.join(runsDir, runId, "run.json")
    const metricsFile = path.join(runsDir, runId, "metrics.parquet")
    if (!(await exists(metaFile)) || !(await exists(metricsFile))) continue

    const { mtimeMs } = await stat(metricsFile)
    const cached = runCache.get(metricsFile)
    if (cached && cached.mtimeMs === mtimeMs) return cached.data

    const data = Promise.all([
      readFile(metaFile, "utf8").then((text) => JSON.parse(text) as Run),
      readParquet(metricsFile).then((rows) => rows.map(toMetric)),
    ]).then(([run, metrics]) => ({ run, metrics }))
    runCache.set(metricsFile, { mtimeMs, data })
    return data
  }
  return null
}

function toMetric(row: Record<string, unknown>): BacktestMetric {
  return {
    run_id: String(row.run_id ?? ""),
    model: String(row.model),
    horizon: toNumber(row.horizon),
    metric: String(row.metric) as BacktestMetric["metric"],
    value: toNumber(row.value),
    segment: String(row.segment),
  }
}

async function readParquet(file: string): Promise<Record<string, unknown>[]> {
  return parquetReadObjects({
    file: await asyncBufferFromFile(file),
    compressors,
  })
}

// Parquet Int64 arrives as bigint (Number() converts it) and Date as a UTC
// midnight Date.
function toNumber(value: unknown): number {
  return Number(value)
}

function toNullableNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null
  const n = toNumber(value)
  return Number.isFinite(n) ? n : null
}

function toIsoDate(value: unknown): string {
  return value instanceof Date
    ? value.toISOString().slice(0, 10)
    : String(value)
}

async function exists(file: string): Promise<boolean> {
  try {
    await stat(file)
    return true
  } catch {
    return false
  }
}

async function safeReaddir(dir: string): Promise<string[]> {
  try {
    return await readdir(dir)
  } catch {
    return []
  }
}
