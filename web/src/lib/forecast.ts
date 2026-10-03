// Pure helpers for presenting forecasts. Safe to import on client or server.

import { BENCHMARK_MODEL, HORIZONS, sortModels } from "@/lib/models"
import { shiftMonth } from "@/lib/series"
import type { Forecast, RegionForecast, SeriesPoint } from "@/lib/types"

export type ForecastPathPoint = {
  date: string
  value: number
  lower: number | null
  upper: number | null
}

/** A model's forecast path for charting, anchored at the origin observation. */
export type ForecastOverlay = {
  model: string
  points: ForecastPathPoint[]
  benchmark: ForecastPathPoint[] | null
}

export function findForecast(
  rf: RegionForecast,
  model: string,
  horizon: number
): Forecast | undefined {
  return rf.forecasts.find((f) => f.model === model && f.horizon === horizon)
}

function modelPath(
  rf: RegionForecast,
  model: string
): ForecastPathPoint[] | null {
  const rows = rf.forecasts
    .filter((f) => f.model === model)
    .sort((a, b) => a.horizon - b.horizon)
  if (rows.length === 0) return null
  const origin = {
    date: rf.origin_date,
    value: rf.origin_value,
    lower: rf.origin_value,
    upper: rf.origin_value,
  }
  return [
    origin,
    ...rows.map((f) => ({
      date: f.target_date,
      value: f.value,
      lower: f.lower,
      upper: f.upper,
    })),
  ]
}

export function buildOverlay(rf: RegionForecast): ForecastOverlay | null {
  const points = modelPath(rf, rf.featured_model)
  if (!points) return null
  return {
    model: rf.featured_model,
    points,
    benchmark: modelPath(rf, BENCHMARK_MODEL),
  }
}

export type ChartRow = {
  date: string
  value: number | null
  forecast?: number | null
  band?: [number, number] | null
  benchmark?: number | null
}

/**
 * History plus one row per future month up to the last forecast, so the x-axis
 * stays evenly spaced in time. Forecasts exist only at their horizons; lines
 * connect across the empty months in between.
 */
export function mergeChartRows(
  history: SeriesPoint[],
  overlay: ForecastOverlay | null
): ChartRow[] {
  const rows: ChartRow[] = history.map((p) => ({
    date: p.date,
    value: p.value,
  }))
  if (!overlay || history.length === 0) return rows

  const byMonth = new Map<string, ChartRow>(
    rows.map((r) => [r.date.slice(0, 7), r])
  )
  const origin = overlay.points[0].date
  const last = overlay.points.at(-1)?.date ?? origin
  const monthsAhead = monthDiff(origin, last)
  for (let i = 1; i <= monthsAhead; i++) {
    const month = shiftMonth(origin, i)
    if (!byMonth.has(month)) {
      const row: ChartRow = { date: `${month}-${lastDay(month)}`, value: null }
      rows.push(row)
      byMonth.set(month, row)
    }
  }

  // Anchor at the origin only if it is inside the visible history.
  for (const p of overlay.points) {
    const row = byMonth.get(p.date.slice(0, 7))
    if (!row) continue
    row.forecast = p.value
    row.band = p.lower !== null && p.upper !== null ? [p.lower, p.upper] : null
  }
  for (const p of overlay.benchmark ?? []) {
    const row = byMonth.get(p.date.slice(0, 7))
    if (row) row.benchmark = p.value
  }
  return rows
}

export type ComparisonRow = {
  model: string
  cells: { horizon: number; forecast: Forecast | undefined }[]
}

/** Every model's forecast at each horizon. */
export function comparisonRows(rf: RegionForecast): ComparisonRow[] {
  return sortModels(rf.forecasts.map((f) => f.model)).map((model) => ({
    model,
    cells: HORIZONS.map((horizon) => ({
      horizon,
      forecast: findForecast(rf, model, horizon),
    })),
  }))
}

function monthDiff(from: string, to: string): number {
  return (
    (Number(to.slice(0, 4)) - Number(from.slice(0, 4))) * 12 +
    Number(to.slice(5, 7)) -
    Number(from.slice(5, 7))
  )
}

/** "2026-02" → "28". */
function lastDay(month: string): string {
  const [y, m] = month.split("-").map(Number)
  return String(new Date(Date.UTC(y, m, 0)).getUTCDate()).padStart(2, "0")
}
