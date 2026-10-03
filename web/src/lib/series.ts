// Pure helpers for time series shown in the UI. Safe to import on client or server.

import type { SeriesPoint, ValueUnit } from "@/lib/types"

export const RANGES = [
  { id: "1y", label: "1Y", years: 1 },
  { id: "3y", label: "3Y", years: 3 },
  { id: "5y", label: "5Y", years: 5 },
  { id: "10y", label: "10Y", years: 10 },
  { id: "max", label: "Max", years: null },
] as const

export type RangeId = (typeof RANGES)[number]["id"]

export const DEFAULT_RANGE: RangeId = "5y"

export function isRangeId(value: unknown): value is RangeId {
  return RANGES.some((r) => r.id === value)
}

export type ValuePoint = { date: string; value: number }

/** Drops leading/trailing gaps; keeps interior nulls so charts show real gaps. */
export function trimNulls(points: SeriesPoint[]): SeriesPoint[] {
  const first = points.findIndex((p) => p.value !== null)
  if (first === -1) return []
  let last = points.length - 1
  while (points[last].value === null) last--
  return points.slice(first, last + 1)
}

/**
 * Points within the range, anchored on the latest observation. The window is
 * inclusive at both ends, so "1Y" spans 13 month-ends and its first-to-last
 * change equals the 12-month change.
 */
export function filterByRange(
  points: SeriesPoint[],
  range: RangeId
): SeriesPoint[] {
  const trimmed = trimNulls(points)
  const years = RANGES.find((r) => r.id === range)?.years ?? null
  if (years === null || trimmed.length === 0) return trimmed

  const lastDate = trimmed[trimmed.length - 1].date
  const cutoff = `${Number(lastDate.slice(0, 4)) - years}${lastDate.slice(4, 7)}`
  return trimmed.filter((p) => p.date.slice(0, 7) >= cutoff)
}

export type Change = { absolute: number; percent: number; from: ValuePoint }

export type SeriesKpis = {
  latest: ValuePoint
  monthChange: Change | null
  yearChange: Change | null
  rangeChange: Change | null
  rangeHigh: ValuePoint
}

/**
 * Headline stats. Month and year changes look up the exact prior month-end in
 * the full history, so they don't depend on the selected range.
 */
export function computeKpis(
  allPoints: SeriesPoint[],
  rangePoints: SeriesPoint[]
): SeriesKpis | null {
  const observed = allPoints.filter(isObserved)
  const inRange = rangePoints.filter(isObserved)
  const latest = observed.at(-1)
  if (!latest || inRange.length === 0) return null

  const byMonth = new Map(observed.map((p) => [p.date.slice(0, 7), p]))
  const monthsBack = (n: number) => byMonth.get(shiftMonth(latest.date, -n))

  const rangeStart = inRange[0]
  const rangeHigh = inRange.reduce((max, p) => (p.value > max.value ? p : max))

  return {
    latest,
    monthChange: change(monthsBack(1), latest),
    yearChange: change(monthsBack(12), latest),
    rangeChange:
      rangeStart.date === latest.date ? null : change(rangeStart, latest),
    rangeHigh,
  }
}

export type Direction = "up" | "down" | "flat"

/** Changes that round to 0.0% read as flat, matching what the UI displays. */
export function changeDirection(percent: number): Direction {
  if (Math.abs(percent) < 0.0005) return "flat"
  return percent > 0 ? "up" : "down"
}

function change(from: ValuePoint | undefined, to: ValuePoint): Change | null {
  if (!from || from.value === 0) return null
  const absolute = to.value - from.value
  return { absolute, percent: absolute / from.value, from }
}

function isObserved(p: SeriesPoint): p is ValuePoint {
  return p.value !== null
}

/** "2026-08-31" shifted by n months → "YYYY-MM". */
export function shiftMonth(date: string, n: number): string {
  const total = Number(date.slice(0, 4)) * 12 + Number(date.slice(5, 7)) - 1 + n
  const year = Math.floor(total / 12)
  const month = (total % 12) + 1
  return `${year}-${String(month).padStart(2, "0")}`
}

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
})

const compactCurrency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
})

const signedPercent = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
  signDisplay: "exceptZero",
})

export const formatCurrency = (value: number) => currency.format(value)
export const formatCompactCurrency = (value: number) =>
  compactCurrency.format(value)
export const formatSignedPercent = (value: number) =>
  signedPercent.format(value)
export const formatSignedCurrency = (value: number) =>
  `${value > 0 ? "+" : value < 0 ? "−" : ""}${currency.format(Math.abs(value))}`

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
]

/** "2026-08-31" → "Aug 2026". Parsed by hand to avoid timezone shifts. */
export function formatMonth(date: string): string {
  return `${MONTHS[Number(date.slice(5, 7)) - 1]} ${date.slice(0, 4)}`
}

/** "2026-08-31" → "Aug '26". */
export function formatShortMonth(date: string): string {
  return `${MONTHS[Number(date.slice(5, 7)) - 1]} '${date.slice(2, 4)}`
}

// --- Unit-aware formatting ---------------------------------------------------
// Dollar and index series change in percent; rate series (already percentages)
// change in percentage points, since "+2% of 6.7%" is easy to misread.

/** Point moves smaller than this read as flat for rate series. */
const FLAT_POINTS = 0.005

/** Signed fixed-point number; values that round to zero get no sign. */
const signed = (n: number, digits: number) => {
  const abs = Math.abs(n).toFixed(digits)
  if (Number(abs) === 0) return abs
  return `${n > 0 ? "+" : "−"}${abs}`
}

export function formatValue(value: number, unit: ValueUnit): string {
  if (unit === "percent") return `${value.toFixed(2)}%`
  if (unit === "index") return value.toFixed(1)
  return formatCurrency(value)
}

export function formatAxisValue(value: number, unit: ValueUnit): string {
  if (unit === "percent") return `${value.toFixed(1)}%`
  if (unit === "index") return value.toFixed(0)
  return formatCompactCurrency(value)
}

export type ChangeDisplay = {
  value: string
  direction: Direction
  detail: string
}

/** Headline value, direction, and detail line for a change, in the unit's terms. */
export function describeChange(change: Change, unit: ValueUnit): ChangeDisplay {
  const since = formatMonth(change.from.date)
  if (unit === "percent") {
    return {
      value: `${signed(change.absolute, 2)} pts`,
      direction: pointDirection(change.absolute),
      detail: `From ${formatValue(change.from.value, unit)} in ${since}`,
    }
  }
  return {
    value: formatSignedPercent(change.percent),
    direction: changeDirection(change.percent),
    detail:
      unit === "index"
        ? `${signed(change.absolute, 1)} index points since ${since}`
        : `${formatSignedCurrency(change.absolute)} since ${since}`,
  }
}

/** Month-over-month change for tables: points for rates, percent otherwise. */
export function describeStep(
  prev: number,
  cur: number,
  unit: ValueUnit
): { text: string; direction: Direction } | null {
  if (unit === "percent") {
    const diff = cur - prev
    return { text: `${signed(diff, 2)} pts`, direction: pointDirection(diff) }
  }
  if (prev === 0) return null
  const pct = (cur - prev) / prev
  return { text: formatSignedPercent(pct), direction: changeDirection(pct) }
}

function pointDirection(diff: number): Direction {
  if (Math.abs(diff) < FLAT_POINTS) return "flat"
  return diff > 0 ? "up" : "down"
}
