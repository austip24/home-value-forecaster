// Plain-language insights from history + forecasts. Pure; safe on client or server.
// The same logic serves Zillow home values and FRED series; wording and "flat"
// thresholds follow the unit (rates move in points, values and indexes in %).

import { findForecast } from "@/lib/forecast"
import { BENCHMARK_MODEL, modelLabel } from "@/lib/models"
import {
  describeStep,
  formatCurrency,
  formatMonth,
  formatSignedPercent,
  formatValue,
  shiftMonth,
  type Direction,
} from "@/lib/series"
import type {
  BacktestMetric,
  MortgageRate,
  RegionForecast,
  SeriesPoint,
  ValueUnit,
} from "@/lib/types"

export type Insight = {
  verdict: string
  tone: Direction
  points: string[]
}

type FlatBand = { rel: number; pts: number }
/** Moves inside this band over the forecast window count as flat. */
const FLAT_FORECAST: FlatBand = { rel: 0.005, pts: 0.1 }
/** Year-over-year moves inside this band count as flat. */
const FLAT_YEAR: FlatBand = { rel: 0.01, pts: 0.1 }
/** Change in 3-month movement that counts as speeding up or slowing down. */
const MOMENTUM_SHIFT: FlatBand = { rel: 0.0025, pts: 0.05 }

/** Size of a move in the unit's natural terms: points for rates, else fraction. */
function delta(from: number, to: number, unit: ValueUnit): number {
  return unit === "percent" ? to - from : to / from - 1
}

function moveDirection(
  from: number,
  to: number,
  unit: ValueUnit,
  band: FlatBand
): Direction {
  const d = delta(from, to, unit)
  const flat = unit === "percent" ? band.pts : band.rel
  return Math.abs(d) < flat ? "flat" : d > 0 ? "up" : "down"
}

/** "+0.12 pts" for rates, "+1.4%" for values and indexes. */
const change = (from: number, to: number, unit: ValueUnit) =>
  describeStep(from, to, unit)?.text ?? "—"

type PathPoint = { date: string; value: number }

function forecastPath(rf: RegionForecast): PathPoint[] {
  const future = rf.forecasts
    .filter((f) => f.model === rf.featured_model)
    .sort((a, b) => a.horizon - b.horizon)
    .map((f) => ({ date: f.target_date, value: f.value }))
  return [{ date: rf.origin_date, value: rf.origin_value }, ...future]
}

/**
 * When to buy (home values) or lock a rate (mortgage rates): lower is better
 * for a buyer in both cases, so the best time is the projected low.
 */
export function buyTimingInsight(
  rf: RegionForecast,
  mortgage: MortgageRate | null = null
): Insight | null {
  const path = forecastPath(rf)
  const last = path.at(-1)
  if (!last || path.length < 2) return null

  const { unit } = rf
  const isRate = rf.dataset === "fred"
  const noun = isRate ? "Rates" : "Values"
  const model = modelLabel(rf.featured_model)
  const today = formatValue(rf.origin_value, unit)
  const points: string[] = []
  let verdict: string
  let tone: Direction

  const allFlat = path.every(
    (p) =>
      moveDirection(rf.origin_value, p.value, unit, FLAT_FORECAST) === "flat"
  )
  const low = path.reduce((min, p) => (p.value < min.value ? p : min))

  if (allFlat) {
    verdict = "No clear timing advantage"
    tone = "flat"
    const band = unit === "percent" ? "±0.1 pts" : "±0.5%"
    points.push(
      `${model} projects ${noun.toLowerCase()} staying within ${band} of today's ${today} through ${formatMonth(last.date)}, so waiting is unlikely to change much.`
    )
  } else if (low.date === rf.origin_date) {
    verdict = isRate
      ? "Locking in sooner looks better than later"
      : "Sooner looks better than later"
    tone = "up"
    points.push(
      `${noun} are projected to rise ${change(rf.origin_value, last.value, unit)} to ${formatValue(last.value, unit)} by ${formatMonth(last.date)}` +
        (unit === "usd"
          ? `, about ${formatCurrency(last.value - rf.origin_value)} more for a typical home than today's ${today}.`
          : `, up from today's ${today}.`)
    )
  } else {
    const subject = isRate ? "rates" : "prices"
    verdict =
      low.date === last.date
        ? `Waiting may pay off; ${subject} projected to keep easing through ${formatMonth(low.date)}`
        : `Waiting may pay off; projected low around ${formatMonth(low.date)}`
    tone = "down"
    points.push(
      `The projected low is ${formatValue(low.value, unit)} around ${formatMonth(low.date)} (${change(rf.origin_value, low.value, unit)} vs. today's ${today}).`
    )
    if (low.date !== last.date) {
      points.push(
        `After that, ${noun.toLowerCase()} are projected to rebound to ${formatValue(last.value, unit)} by ${formatMonth(last.date)}.`
      )
    }
  }

  const year = findForecast(rf, rf.featured_model, 12)
  if (year?.lower != null && year.upper != null) {
    const range = `${formatValue(year.lower, unit)}–${formatValue(year.upper, unit)}`
    points.push(
      year.lower < rf.origin_value && year.upper > rf.origin_value
        ? `Low confidence: the 80% range for ${formatMonth(year.target_date)} (${range}) includes both a rise and a fall from today.`
        : `The 80% range for ${formatMonth(year.target_date)} (${range}) sits entirely ${year.lower >= rf.origin_value ? "above" : "below"} today's value.`
    )
  }

  const zillow = findForecast(rf, BENCHMARK_MODEL, 12)
  if (zillow) {
    const ours = last.value / rf.origin_value - 1
    const zChange = zillow.value / rf.origin_value - 1
    points.push(
      `Zillow's own forecast ${compareToZillow(ours, zChange)}: ${formatSignedPercent(zChange)} by ${formatMonth(zillow.target_date)}.`
    )
  }

  if (mortgage) points.push(mortgageRatePoint(mortgage, rf.origin_date))

  return { verdict, tone, points }
}

/** Borrowing-cost context; a national figure, not part of the price forecast. */
function mortgageRatePoint(m: MortgageRate, originDate: string): string {
  const partial = m.date.slice(0, 7) > originDate.slice(0, 7)
  const base = `30-year mortgage rates averaged ${m.rate.toFixed(2)}% in ${formatMonth(m.date)}${partial ? " (month to date)" : ""}`
  if (m.year_ago === null) return `${base}.`
  const diff = m.rate - m.year_ago
  if (Math.abs(diff) < 0.05) return `${base}, about the same as a year earlier.`
  return `${base}, ${Math.abs(diff).toFixed(2)} points ${diff < 0 ? "lower" : "higher"} than a year earlier, so borrowing costs ${diff < 0 ? "less" : "more"} than it did.`
}

/** How Zillow's projection relates to ours, in direction and size. */
export function compareToZillow(ours: number, zillow: number): string {
  const sign = (x: number) => (x > 0 ? 1 : x < 0 ? -1 : 0)
  if (sign(ours) !== sign(zillow)) {
    // Opposite signs only count as disagreement when either move is material.
    return Math.max(Math.abs(ours), Math.abs(zillow)) < FLAT_FORECAST.rel
      ? "also sees little change"
      : "disagrees on direction"
  }
  const ratio = Math.abs(zillow) / Math.max(Math.abs(ours), 1e-9)
  if (ratio < 0.5) return "agrees on direction but sees a smaller move"
  if (ratio > 2) return "agrees on direction but sees a larger move"
  return "agrees"
}

type TrendInput = {
  regionName: string
  points: SeriesPoint[]
  /** National history to compare against, or null (the nation itself, FRED). */
  nationalPoints: SeriesPoint[] | null
  forecast: RegionForecast
  metrics: BacktestMetric[]
  regionId: number
}

const RECENT_PHRASE: Record<Direction, string> = {
  up: "Rising",
  down: "Declining",
  flat: "Flat",
}

const OUTLOOK_PHRASE: Record<Direction, Record<Direction, string>> = {
  up: {
    up: "and expected to keep rising",
    flat: "but expected to level off",
    down: "but expected to turn down",
  },
  down: {
    up: "but expected to recover",
    flat: "but expected to stabilize",
    down: "and expected to keep declining",
  },
  flat: {
    up: "but expected to pick up",
    flat: "and expected to stay flat",
    down: "but expected to soften",
  },
}

/** Recent trajectory, momentum, national comparison, and outlook. */
export function trendInsight({
  regionName,
  points,
  nationalPoints,
  forecast: rf,
  metrics,
  regionId,
}: TrendInput): Insight | null {
  const { unit } = rf
  // Measure history up to the forecast origin so every number lines up with
  // the forecast (FRED can include a newer, partial month after the origin).
  const known = points.filter((p) => p.date <= rf.origin_date)
  const history = valuesByMonth(known)
  const latest = known.findLast((p) => p.value !== null)
  if (!latest || latest.value === null) return null

  const at = (n: number) => history.get(shiftMonth(latest.date, -n))
  const yearAgo = at(12)
  const outlook = findForecast(rf, rf.featured_model, 12)
  if (yearAgo === undefined || !outlook) return null

  const recentDir = moveDirection(yearAgo, latest.value, unit, FLAT_YEAR)
  const outlookDir = moveDirection(
    rf.origin_value,
    outlook.value,
    unit,
    FLAT_YEAR
  )
  const out: string[] = []

  const momentum = momentumPhrase(latest.value, at(3), at(6), unit)
  out.push(
    `Past 12 months: ${change(yearAgo, latest.value, unit)} (${formatValue(latest.value, unit)} in ${formatMonth(latest.date)}).` +
      (momentum ? ` Over the last 3 months it ${momentum}.` : "")
  )

  if (nationalPoints) {
    const national = valuesByMonth(nationalPoints)
    const nNow = national.get(latest.date.slice(0, 7))
    const nYearAgo = national.get(shiftMonth(latest.date, -12))
    if (nNow && nYearAgo && unit === "percent") {
      // Rates: compare movements in points, without implying good or bad.
      out.push(
        `Nationally, the rate moved ${change(nYearAgo, nNow, unit)} over the same 12 months, to ${formatValue(nNow, unit)}.`
      )
    } else if (nNow && nYearAgo) {
      const nChange = nNow / nYearAgo - 1
      const gap = latest.value / yearAgo - 1 - nChange
      const relation =
        Math.abs(gap) < FLAT_FORECAST.rel
          ? "tracking"
          : gap > 0
            ? "outpacing"
            : "lagging"
      out.push(
        `Nationally, values moved ${formatSignedPercent(nChange)}, so ${regionName} is ${relation} the U.S. market.`
      )
    }
  }

  const zillow = findForecast(rf, BENCHMARK_MODEL, 12)
  out.push(
    `Next 12 months: ${modelLabel(rf.featured_model)} projects ${change(rf.origin_value, outlook.value, unit)} to ${formatValue(outlook.value, unit)} by ${formatMonth(outlook.target_date)}` +
      (zillow
        ? `; Zillow projects ${formatSignedPercent(zillow.value / rf.origin_value - 1)}.`
        : ".")
  )

  const record = trackRecord(metrics, rf, regionId)
  if (record) {
    out.push(
      `Track record: ${modelLabel(rf.featured_model)} called the 12-month direction correctly in ${Math.round(record.accuracy * 100)}% of backtests ${record.scope}` +
        (record.mape !== null
          ? `, with a typical error of ${record.mape.toFixed(1)}%.`
          : ".")
    )
  }

  return {
    verdict: `${RECENT_PHRASE[recentDir]}, ${OUTLOOK_PHRASE[recentDir][outlookDir]}`,
    tone: outlookDir,
    points: out,
  }
}

/** How the latest 3-month move compares with the 3 months before it. */
function momentumPhrase(
  now: number,
  threeAgo: number | undefined,
  sixAgo: number | undefined,
  unit: ValueUnit
): string | null {
  if (threeAgo === undefined || sixAgo === undefined) return null
  const recent = delta(threeAgo, now, unit)
  const prior = delta(sixAgo, threeAgo, unit)
  const pace =
    unit === "percent"
      ? `${change(threeAgo, now, unit)} over 3 months`
      : `${formatSignedPercent((1 + recent) ** 4 - 1)} annualized`
  const shiftBand = unit === "percent" ? MOMENTUM_SHIFT.pts : MOMENTUM_SHIFT.rel
  const shift = recent - prior

  if (recent >= 0 && prior < 0) return `turned up (${pace})`
  if (recent < 0 && prior >= 0) return `turned down (${pace})`
  const verb = recent >= 0 ? "rising" : "falling"
  const faster = recent >= 0 ? shift > shiftBand : shift < -shiftBand
  const slower = recent >= 0 ? shift < -shiftBand : shift > shiftBand
  const speed = faster ? "faster" : slower ? "more slowly" : "at a steady pace"
  return `has been ${verb} ${speed} (${pace})`
}

function trackRecord(
  metrics: BacktestMetric[],
  rf: RegionForecast,
  regionId: number
): { accuracy: number; mape: number | null; scope: string } | null {
  const find = (metric: BacktestMetric["metric"], segment: string) =>
    metrics.find(
      (m) =>
        m.model === rf.featured_model &&
        m.horizon === 12 &&
        m.metric === metric &&
        m.segment === segment
    )?.value
  const scopes =
    rf.dataset === "fred"
      ? ([
          [`region:${regionId}`, "for this series"],
          ["all", "across all FRED series"],
        ] as const)
      : ([
          [`region:${regionId}`, "for this metro"],
          ["all", "across all metros"],
        ] as const)
  for (const [segment, scope] of scopes) {
    const accuracy = find("directional_accuracy", segment)
    if (accuracy !== undefined) {
      return { accuracy, mape: find("mape", segment) ?? null, scope }
    }
  }
  return null
}

function valuesByMonth(points: SeriesPoint[]): Map<string, number> {
  const map = new Map<string, number>()
  for (const p of points)
    if (p.value !== null) map.set(p.date.slice(0, 7), p.value)
  return map
}
