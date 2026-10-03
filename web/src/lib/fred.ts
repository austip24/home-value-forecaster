// FRED series shown in the dashboard. Pure; safe to import on client or server.
// File patterns match the forecaster's snapshot names (forecaster/src/forecaster/sources.py).

import type { SeriesOption, ValueUnit } from "@/lib/types"

export type FredSeries = SeriesOption & {
  /** FRED series id, for attribution and links. */
  fredId: string
  /** Forecast-subject id the forecaster uses (FredSource.region_id). */
  key: number
  /**
   * Matches the national snapshot file in data/raw/fred/<release>/. Keep these
   * specific: the metro family (unrate_metro_*.csv) shares the same prefix.
   */
  filePattern: RegExp
  unit: ValueUnit
  description: string
  /** The series as a sentence subject, e.g. "the unemployment rate". */
  subject: string
}

export const FRED_SERIES: FredSeries[] = [
  {
    id: "mortgage_rate",
    label: "30-year mortgage rate",
    fredId: "MORTGAGE30US",
    key: 900001,
    filePattern: /^mortgage30_national_.*\.csv$/,
    unit: "percent",
    description:
      "Freddie Mac 30-year fixed-rate mortgage average · monthly average of weekly readings",
    subject: "the 30-year mortgage rate",
  },
  {
    id: "unemployment",
    label: "Unemployment rate",
    fredId: "UNRATE",
    key: 900002,
    filePattern: /^unrate_national_.*\.csv$/,
    unit: "percent",
    description: "U.S. civilian unemployment rate · seasonally adjusted",
    subject: "the unemployment rate",
  },
  {
    id: "cpi",
    label: "Consumer Price Index",
    fredId: "CPIAUCSL",
    key: 900003,
    filePattern: /^cpi_national_.*\.csv$/,
    unit: "index",
    description:
      "CPI for all urban consumers, all items · seasonally adjusted, index 1982–84 = 100",
    subject: "the Consumer Price Index",
  },
]

export const DEFAULT_FRED_SERIES = FRED_SERIES[0].id

export function findFredSeries(id: unknown): FredSeries | undefined {
  return FRED_SERIES.find((s) => s.id === id)
}

/** FRED data is national; the dashboard shows it as one "United States" region. */
export const FRED_REGION = {
  region_id: 102001, // Zillow's United States RegionID, so links between providers line up
  region_name: "United States",
  state: null,
  size_rank: 0,
  region_type: "country",
}
