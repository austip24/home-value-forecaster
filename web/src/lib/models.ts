// Forecast model metadata and selection. Pure; safe to import on client or server.

import type { BacktestMetric } from "@/lib/types"

export const HORIZONS = [1, 3, 12] as const

export const BENCHMARK_MODEL = "zhvf"

type ModelInfo = { label: string; kind: string; description: string }

const MODELS: Record<string, ModelInfo> = {
  naive: {
    label: "Naive",
    kind: "Baseline",
    description:
      "Assumes the value stays exactly where it is today. The simplest possible forecast, and the bar every other model has to clear.",
  },
  seasonal_naive: {
    label: "Seasonal naive",
    kind: "Baseline",
    description:
      "Repeats the value from the same month last year. A standard baseline, but weak here because this ZHVI series is already seasonally adjusted.",
  },
  rw_drift: {
    label: "Random walk + drift",
    kind: "Baseline",
    description:
      "Extends the metro's long-run average monthly growth rate in a straight line from today's value.",
  },
  auto_ets: {
    label: "AutoETS",
    kind: "Statistical",
    description:
      "Exponential smoothing: a weighted average where recent months count more, tracking the current level and trend. Automatically picks the best-fitting variant for each metro.",
  },
  auto_arima: {
    label: "AutoARIMA",
    kind: "Statistical",
    description:
      "AutoRegressive Integrated Moving Average: predicts each month's change from the metro's recent changes and recent forecast errors. Automatically searches for the best-fitting configuration for each metro.",
  },
  lightgbm: {
    label: "LightGBM",
    kind: "Global ML",
    description:
      "A gradient-boosted decision tree model trained on all metros at once. Learns from recent price momentum, listing and inventory signals, and macro data like mortgage rates, unemployment, and inflation.",
  },
  zhvf: {
    label: "Zillow forecast (ZHVF)",
    kind: "Benchmark",
    description:
      "Zillow's own published Home Value Forecast, converted from growth rates to dollar values. Used as the benchmark to beat.",
  },
}

/** Build order from the forecaster: baselines → statistical → ML → benchmark. */
export const MODEL_ORDER = Object.keys(MODELS)

export const modelLabel = (model: string) => MODELS[model]?.label ?? model
export const modelKind = (model: string) => MODELS[model]?.kind ?? "Model"
export const modelDescription = (model: string) =>
  MODELS[model]?.description ?? null

export function sortModels(models: Iterable<string>): string[] {
  const rank = (m: string) => {
    const i = MODEL_ORDER.indexOf(m)
    return i === -1 ? MODEL_ORDER.length : i
  }
  return [...new Set(models)].sort(
    (a, b) => rank(a) - rank(b) || a.localeCompare(b)
  )
}

// Used when no backtest exists yet: most sophisticated model first.
const FALLBACK_PREFERENCE = [
  "lightgbm",
  "auto_arima",
  "auto_ets",
  "rw_drift",
  "naive",
]

/**
 * The model to lead with: lowest mean MASE across horizons on all subjects
 * (metros or FRED series), among models that have forecasts. ZHVF is never
 * featured; it is the yardstick.
 */
export function pickFeaturedModel(
  metrics: BacktestMetric[],
  available: Iterable<string>
): string | null {
  const candidates = new Set(
    [...available].filter((m) => m !== BENCHMARK_MODEL)
  )
  const sums = new Map<string, { total: number; n: number }>()
  for (const m of metrics) {
    if (m.metric !== "mase" || m.segment !== "all" || !candidates.has(m.model))
      continue
    const s = sums.get(m.model) ?? { total: 0, n: 0 }
    sums.set(m.model, { total: s.total + m.value, n: s.n + 1 })
  }

  let best: { model: string; mean: number } | null = null
  for (const [model, { total, n }] of sums) {
    // Only rank models scored at every horizon.
    if (n < HORIZONS.length) continue
    const mean = total / n
    if (!best || mean < best.mean) best = { model, mean }
  }
  return (
    best?.model ?? FALLBACK_PREFERENCE.find((m) => candidates.has(m)) ?? null
  )
}
