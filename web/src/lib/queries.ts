// Typed read queries used by server components.
// History comes from raw CSV snapshots (raw-data.ts) and forecasts from the
// forecaster's processed outputs (forecast-data.ts); both will move to
// Postgres (lib/db.ts), which the forecaster's `publish` step already fills.

import {
  loadForecasts,
  loadLatestRun,
  loadMacro,
  loadMetroUnemployment,
} from "@/lib/forecast-data"
import {
  DEFAULT_FRED_SERIES,
  FRED_REGION,
  FRED_SERIES,
  findFredSeries,
  type FredSeries,
} from "@/lib/fred"
import { pickFeaturedModel } from "@/lib/models"
import { findLatestSnapshot, loadDataset, loadFredSeries } from "@/lib/raw-data"
import { shiftMonth } from "@/lib/series"
import type {
  DatasetId,
  ModelPerformance,
  MortgageRate,
  Mover,
  Provider,
  ProviderId,
  RegionForecast,
  RegionOption,
  RegionSeries,
  SeriesPoint,
  ValueUnit,
} from "@/lib/types"

const PROVIDER_META: Record<ProviderId, Omit<Provider, "release">> = {
  zillow: {
    id: "zillow",
    label: "Zillow Research",
    metric: "ZHVI",
    metricDescription:
      "Zillow Home Value Index · all homes, mid-tier, smoothed & seasonally adjusted",
  },
  redfin: {
    id: "redfin",
    label: "Redfin Data Center",
    metric: "Median sale price",
    metricDescription: "Redfin median sale price · metro",
  },
  fred: {
    id: "fred",
    label: "FRED (St. Louis Fed)",
    metric: "Macro indicators",
    metricDescription:
      "Federal Reserve Economic Data · national mortgage rates, unemployment, and inflation",
  },
}

export const PROVIDER_IDS = Object.keys(PROVIDER_META) as ProviderId[]

export function isProviderId(value: unknown): value is ProviderId {
  return typeof value === "string" && value in PROVIDER_META
}

export async function getProviders(): Promise<Provider[]> {
  return Promise.all(
    PROVIDER_IDS.map(async (id) => {
      const snapshot = await findLatestSnapshot(id)
      return { ...PROVIDER_META[id], release: snapshot?.release ?? null }
    })
  )
}

export async function getRegions(
  provider: ProviderId
): Promise<RegionOption[]> {
  if (provider === "fred") {
    // National series, plus every metro FRED publishes unemployment for.
    const metro = await loadMetroUnemployment()
    return [FRED_REGION, ...(metro?.metros.map((m) => m.region) ?? [])]
  }
  const dataset = await loadDataset(provider)
  return dataset?.regions ?? []
}

export async function getRegionSeries(
  provider: ProviderId,
  regionId: number,
  seriesId?: string
): Promise<RegionSeries | null> {
  if (provider === "fred") {
    return regionId === FRED_REGION.region_id
      ? getFredSeries(seriesId)
      : ((await getFredMetroSeries(regionId)) ?? getFredSeries(seriesId))
  }
  const dataset = await loadDataset(provider)
  if (!dataset) return null

  const region = dataset.regions.find((r) => r.region_id === regionId)
  const points = dataset.series.get(regionId)
  if (!region || !points) return null

  return {
    region,
    provider,
    metric: PROVIDER_META[provider].metric,
    description: PROVIDER_META[provider].metricDescription,
    unit: "usd",
    series_id: null,
    release: dataset.release,
    points,
  }
}

/** A national FRED series, falling back to the default when unknown. */
async function getFredSeries(seriesId?: string): Promise<RegionSeries | null> {
  const series = findFredSeries(seriesId) ?? findFredSeries(DEFAULT_FRED_SERIES)
  if (!series) return null
  const loaded = await loadFredSeries(series.id)
  if (!loaded) return null
  return {
    region: FRED_REGION,
    provider: "fred",
    metric: series.label,
    description: `${series.description} · FRED ${series.fredId}`,
    unit: series.unit,
    series_id: series.id,
    release: loaded.release,
    points: loaded.points,
  }
}

/**
 * A metro's FRED unemployment rate. Mortgage rates and CPI are national only,
 * so metros always show unemployment, whatever series was requested.
 */
async function getFredMetroSeries(
  regionId: number
): Promise<RegionSeries | null> {
  const metro = await loadMetroUnemployment()
  const match = metro?.metros.find((m) => m.region.region_id === regionId)
  const points = metro?.series.get(regionId)
  const unemployment = findFredSeries("unemployment")
  if (!metro || !match || !points || !unemployment) return null
  return {
    region: match.region,
    provider: "fred",
    metric: unemployment.label,
    description: `Unemployment rate in ${match.fredName} · smoothed seasonally adjusted · FRED ${match.seriesId}`,
    unit: "percent",
    series_id: unemployment.id,
    release: metro.release,
    points,
  }
}

/** Backtest metrics for the release the current forecasts came from. */
export async function getModelPerformance(
  dataset: DatasetId = "zillow"
): Promise<ModelPerformance | null> {
  const forecasts = await loadForecasts(dataset)
  return forecasts ? loadLatestRun(forecasts.release, dataset) : null
}

async function getFeaturedModel(dataset: DatasetId): Promise<string | null> {
  const forecasts = await loadForecasts(dataset)
  if (!forecasts) return null
  const performance = await loadLatestRun(forecasts.release, dataset)
  const available = new Set<string>()
  for (const rows of forecasts.byRegion.values()) {
    for (const row of rows) available.add(row.model)
  }
  return pickFeaturedModel(performance?.metrics ?? [], available)
}

/** Value at the forecast origin, from the same snapshot the chart shows. */
async function originValue(
  dataset: DatasetId,
  regionId: number,
  originDate: string
): Promise<number | null> {
  if (dataset === "fred") {
    const series = FRED_SERIES.find((s) => s.key === regionId)
    const loaded = series ? await loadFredSeries(series.id) : null
    return loaded?.points.find((p) => p.date === originDate)?.value ?? null
  }
  if (dataset === "fred_metro") {
    const metro = await loadMetroUnemployment()
    const points = metro?.series.get(regionId)
    return points?.find((p) => p.date === originDate)?.value ?? null
  }
  const zillow = await loadDataset("zillow")
  const point = zillow?.series.get(regionId)?.find((p) => p.date === originDate)
  return point?.value ?? null
}

/**
 * Forecasts for one subject: a Zillow metro (RegionID) or a FRED series
 * (its forecaster key, e.g. 900001 for the mortgage rate).
 */
export async function getRegionForecast(
  regionId: number,
  dataset: DatasetId = "zillow"
): Promise<RegionForecast | null> {
  const [forecasts, featured] = await Promise.all([
    loadForecasts(dataset),
    getFeaturedModel(dataset),
  ])
  const rows = forecasts?.byRegion.get(regionId)
  if (!forecasts || !rows || !featured) return null

  const value = await originValue(dataset, regionId, forecasts.originDate)
  if (value === null) return null

  const unit: ValueUnit =
    dataset === "fred"
      ? (FRED_SERIES.find((s) => s.key === regionId)?.unit ?? "index")
      : dataset === "fred_metro"
        ? "percent"
        : "usd"
  return {
    release: forecasts.release,
    origin_date: forecasts.originDate,
    origin_value: value,
    featured_model: featured,
    forecasts: rows,
    dataset,
    unit,
  }
}

/** Every FRED series' featured 12-month forecast: the macro counterpart of movers. */
export async function getFredOutlook(): Promise<{
  model: string
  items: { series: FredSeries; forecast: RegionForecast }[]
} | null> {
  const featured = await getFeaturedModel("fred")
  if (!featured) return null
  const items = (
    await Promise.all(
      FRED_SERIES.map(async (series) => {
        const forecast = await getRegionForecast(series.key, "fred")
        return forecast ? { series, forecast } : null
      })
    )
  ).filter((item) => item !== null)
  return items.length ? { model: featured, items } : null
}

/**
 * Largest projected 12-month rises and falls among the biggest metros, using
 * the featured model: home values (Zillow) or unemployment rates (FRED metro).
 * Changes rank in the unit's natural terms: percent for values, points for rates.
 */
export async function getMovers({
  dataset = "zillow",
  limit = 5,
  maxSizeRank = 100,
}: {
  dataset?: "zillow" | "fred_metro"
  limit?: number
  maxSizeRank?: number
} = {}): Promise<{
  model: string
  unit: ValueUnit
  gainers: Mover[]
  decliners: Mover[]
} | null> {
  const [forecasts, featured] = await Promise.all([
    loadForecasts(dataset),
    getFeaturedModel(dataset),
  ])
  if (!forecasts || !featured) return null

  let candidates: { region: RegionOption; points: SeriesPoint[] | undefined }[]
  if (dataset === "fred_metro") {
    const metro = await loadMetroUnemployment()
    candidates = (metro?.metros ?? []).map((m) => ({
      region: m.region,
      points: metro?.series.get(m.region.region_id),
    }))
  } else {
    const zillow = await loadDataset("zillow")
    candidates = (zillow?.regions ?? []).map((region) => ({
      region,
      points: zillow?.series.get(region.region_id),
    }))
  }
  const unit: ValueUnit = dataset === "fred_metro" ? "percent" : "usd"

  const movers: Mover[] = []
  for (const { region, points } of candidates) {
    if (
      region.region_type !== "msa" ||
      (region.size_rank ?? Infinity) > maxSizeRank
    ) {
      continue
    }
    const forecast = forecasts.byRegion
      .get(region.region_id)
      ?.find((f) => f.model === featured && f.horizon === 12)
    const base = points?.find((p) => p.date === forecasts.originDate)?.value
    if (!forecast || !base) continue
    movers.push({
      region,
      origin_value: base,
      forecast,
      change:
        unit === "percent" ? forecast.value - base : forecast.value / base - 1,
    })
  }

  movers.sort((a, b) => b.change - a.change)
  return {
    model: featured,
    unit,
    gainers: movers.slice(0, limit),
    decliners: movers.slice(-limit).reverse(),
  }
}

/**
 * Latest 30-year mortgage rate (monthly average of Freddie Mac's weekly survey)
 * from the FRED snapshot behind the current forecasts.
 */
export async function getMortgageRate(): Promise<MortgageRate | null> {
  const forecasts = await loadForecasts()
  if (!forecasts) return null
  const rates = (await loadMacro(forecasts.release))
    .filter((p) => p.metric === "mortgage_rate")
    .sort((a, b) => a.date.localeCompare(b.date))
  const latest = rates.at(-1)
  if (!latest) return null
  const yearAgo = rates.find(
    (p) => p.date.slice(0, 7) === shiftMonth(latest.date, -12)
  )
  return {
    date: latest.date,
    rate: latest.value,
    year_ago: yearAgo?.value ?? null,
  }
}
