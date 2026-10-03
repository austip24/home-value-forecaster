// Types mirroring the database contract in forecaster/migrations/.
// Keep in sync with any schema change there.

export type Region = {
  region_id: number
  region_name: string
  state: string | null
  size_rank: number | null
}

export type Observation = {
  region_id: number
  date: string // ISO date, month-end (YYYY-MM-DD)
  metric: string
  value: number | null
  release: string // YYYY-MM
}

export type Forecast = {
  region_id: number
  origin_date: string
  target_date: string
  horizon: number
  model: string
  value: number
  lower: number | null
  upper: number | null
  /** What is forecast: zhvi, mortgage_rate, unemployment, cpi (migration 002). */
  target: string
  release: string
}

export type BacktestMetric = {
  run_id: string
  model: string
  horizon: number
  metric: "mase" | "mape" | "directional_accuracy"
  value: number
  segment: string
}

export type Run = {
  run_id: string
  release: string
  git_sha: string
  config: Record<string, unknown>
  created_at: string
}

// App-level types (not tables).

export type ProviderId = "zillow" | "redfin" | "fred"

/** How a series' values are measured, which decides how they are formatted. */
export type ValueUnit = "usd" | "percent" | "index"

/** A selectable series within a provider that offers several (e.g. FRED). */
export type SeriesOption = {
  id: string
  label: string
  /** Not available for the selected location (e.g. national-only series). */
  disabled?: boolean
  /** Shown beside the label, e.g. why it is disabled. */
  note?: string
}

export type Provider = {
  id: ProviderId
  label: string
  metric: string
  metricDescription: string
  /** Latest release folder on disk (YYYY-MM), or null when no data exists yet. */
  release: string | null
}

export type RegionOption = Region & {
  region_type: string
}

export type SeriesPoint = {
  date: string
  value: number | null
}

export type RegionSeries = {
  region: RegionOption
  provider: ProviderId
  metric: string
  /** Longer description of the metric, shown under the chart title. */
  description: string
  unit: ValueUnit
  /** Which of the provider's series this is, when it offers several. */
  series_id: string | null
  release: string
  points: SeriesPoint[]
}

/** Forecasts for one region from the latest forecaster release. */
export type RegionForecast = {
  release: string
  /** Last observed month-end the forecasts start from. */
  origin_date: string
  /** ZHVI at the origin, the base for percent changes. */
  origin_value: number
  /** Model the UI leads with: best mean backtest MASE across horizons. */
  featured_model: string
  forecasts: Forecast[]
  /** Which forecaster dataset produced these: Zillow metros or FRED series. */
  dataset: DatasetId
  unit: ValueUnit
}

export type DatasetId = "zillow" | "fred" | "fred_metro"

/** Latest backtest run for a release and its metrics. */
export type ModelPerformance = {
  run: Run
  metrics: BacktestMetric[]
}

export type Mover = {
  region: RegionOption
  origin_value: number
  forecast: Forecast
  /** Fractional change from origin to forecast. */
  change: number
}

/** One month of a national macro series (monthly mean), from FRED. */
export type MacroPoint = {
  date: string // month-end
  metric: string // mortgage_rate | unemployment | cpi
  value: number
}

export type MortgageRate = {
  /** Month-end of the latest monthly average. */
  date: string
  /** 30-year fixed rate, percent. */
  rate: number
  /** Same month a year earlier, if available. */
  year_ago: number | null
}
