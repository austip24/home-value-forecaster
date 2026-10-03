"use client"

import { useState } from "react"

import { ModelName } from "@/components/forecast/model-name"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { FRED_SERIES } from "@/lib/fred"
import { HORIZONS, sortModels } from "@/lib/models"
import type {
  BacktestMetric,
  DatasetId,
  ModelPerformance as Performance,
} from "@/lib/types"
import { cn } from "@/lib/utils"

type MetricId = BacktestMetric["metric"]

const METRICS: {
  id: MetricId
  label: string
  lowerIsBetter: boolean
  hint: string
}[] = [
  {
    id: "mase",
    label: "MASE",
    lowerIsBetter: true,
    hint: "Error scaled by each metro's typical one-month change. Compare models within a horizon; it grows with horizon length.",
  },
  {
    id: "mape",
    label: "MAPE",
    lowerIsBetter: true,
    hint: "Mean absolute percentage error.",
  },
  {
    id: "directional_accuracy",
    label: "Direction",
    lowerIsBetter: false,
    hint: "Share of forecasts that called the direction of change correctly.",
  },
]

type ModelPerformanceProps = {
  performance: Performance
  regionId: number
  regionName: string
  featuredModel: string | null
  dataset: DatasetId
}

export function ModelPerformance({
  performance,
  regionId,
  regionName,
  featuredModel,
  dataset,
}: ModelPerformanceProps) {
  // National FRED series and FRED metro unemployment share FRED wording.
  const isFred = dataset !== "zillow"
  const { run, metrics } = performance
  const [metric, setMetric] = useState<MetricId>("mase")
  // FRED has three series, so each is its own segment (like Zillow's tiers);
  // for Zillow only the selected metro is added, when it is a showcase metro.
  const subjects: [number, string][] =
    dataset === "fred"
      ? FRED_SERIES.map((s) => [s.key, s.label])
      : [[regionId, regionName]]
  const segments = availableSegments(
    metrics,
    dataset === "fred" ? "All FRED series" : "All metros",
    subjects
  )
  const [segment, setSegment] = useState("all")
  const activeSegment = segments.some((s) => s.value === segment)
    ? segment
    : "all"

  const info = METRICS.find((m) => m.id === metric) ?? METRICS[0]
  const rows = metrics.filter(
    (m) => m.metric === metric && m.segment === activeSegment
  )
  const models = sortModels(rows.map((r) => r.model))
  const cell = (model: string, horizon: number) =>
    rows.find((r) => r.model === model && r.horizon === horizon)?.value
  const best = Object.fromEntries(
    HORIZONS.map((h) => {
      const values = models
        .map((m) => cell(m, h))
        .filter((v) => v !== undefined)
      return [h, info.lowerIsBetter ? Math.min(...values) : Math.max(...values)]
    })
  )

  const config = run.config as {
    origins?: string[]
    data_vintage?: string
    models?: string[]
    inputs?: { market?: string[]; macro?: string[] }
  }
  const usesGlobalModel = config.models?.includes("lightgbm") ?? false
  const origins = config.origins ?? []

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Model performance</CardTitle>
        <CardDescription>
          Rolling-origin backtest over {origins.length} monthly origins
          {origins.length > 0 &&
            ` (${origins[0].slice(0, 7)} to ${origins[origins.length - 1].slice(0, 7)})`}
          .
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <Tabs
            value={metric}
            onValueChange={(value) => {
              const next = METRICS.find((m) => m.id === value)
              if (next) setMetric(next.id)
            }}
          >
            <TabsList aria-label="Metric">
              {METRICS.map((m) => (
                <TabsTrigger key={m.id} value={m.id} className="px-3">
                  {m.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <Select
            value={activeSegment}
            onValueChange={(value) => {
              if (typeof value === "string") setSegment(value)
            }}
            items={segments}
          >
            <SelectTrigger aria-label="Segment" className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {segments.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <p className="text-xs text-muted-foreground">{info.hint}</p>

        <div className="overflow-x-auto rounded-lg border">
          <Table>
            <caption className="sr-only">
              {info.label} by model and forecast horizon
            </caption>
            <TableHeader>
              <TableRow>
                <TableHead>Model</TableHead>
                {HORIZONS.map((h) => (
                  <TableHead key={h} className="text-right">
                    {h}-month
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {models.map((model) => (
                <TableRow key={model}>
                  <TableCell>
                    <span className="flex items-center gap-2">
                      <ModelName model={model} />
                      {model === featuredModel && (
                        <Badge variant="secondary">Featured</Badge>
                      )}
                    </span>
                  </TableCell>
                  {HORIZONS.map((h) => {
                    const value = cell(model, h)
                    return (
                      <TableCell
                        key={h}
                        className={cn(
                          "text-right font-mono tabular-nums",
                          value !== undefined &&
                            value === best[h] &&
                            "font-semibold"
                        )}
                      >
                        {value === undefined
                          ? "—"
                          : formatMetric(metric, value)}
                      </TableCell>
                    )
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
      <CardFooter className="flex flex-col items-start gap-1 border-t py-3 text-xs text-muted-foreground">
        <span>
          Run {run.run_id} · Release {run.release} · Commit{" "}
          {run.git_sha.slice(0, 7)}
          {run.git_sha.endsWith("-dirty") && " (uncommitted changes)"}
        </span>
        {usesGlobalModel && config.inputs && (
          <span>
            {describeInputs(
              config.inputs,
              dataset === "fred"
                ? "each series' own momentum"
                : dataset === "fred_metro"
                  ? "each metro's unemployment momentum"
                  : "home value momentum"
            )}
          </span>
        )}
        {config.data_vintage === "current" && (
          <span>
            Backtested on current-vintage data: no archived snapshots existed
            for these origins, so later {isFred ? "FRED" : "Zillow"} revisions
            are visible to the models.
          </span>
        )}
        {!isFred && !metrics.some((m) => m.model === "zhvf") && (
          <span>
            Zillow&apos;s forecast can only be scored once its archived
            snapshots reach a backtest origin.
          </span>
        )}
      </CardFooter>
    </Card>
  )
}

const INPUT_LABELS: Record<string, string> = {
  inventory: "inventory",
  new_listings: "new listings",
  new_pending: "newly pending sales",
  price_cut_share: "price cuts",
  days_to_pending: "days to pending",
  market_heat: "market heat",
  sale_to_list: "sale-to-list ratio",
  mortgage_rate: "30-year mortgage rate",
  unemployment: "unemployment rate",
  cpi: "CPI inflation",
}

const listInputs = (names: string[]) =>
  names.map((n) => INPUT_LABELS[n] ?? n).join(", ")

/** The data LightGBM was trained on in this run, in plain words. */
function describeInputs(
  inputs: { market?: string[]; macro?: string[] },
  momentum: string
) {
  const market = inputs.market ?? []
  const macro = inputs.macro ?? []
  const parts = [momentum]
  if (market.length) parts.push(`Zillow market data (${listInputs(market)})`)
  parts.push(
    macro.length
      ? `FRED macro data (${listInputs(macro)})`
      : "no macro data (FRED key not set for this run)"
  )
  return `LightGBM inputs: ${parts.join("; ")}.`
}

function formatMetric(metric: MetricId, value: number): string {
  if (metric === "mase") return value.toFixed(2)
  if (metric === "mape") return `${value.toFixed(2)}%`
  return `${(value * 100).toFixed(0)}%`
}

const SEGMENT_LABELS: Record<string, string> = {
  national: "United States",
  "size:1-50": "Largest 50 metros",
  "size:51-200": "Metros ranked 51–200",
  "size:201+": "Metros ranked 201+",
  benchmark_matched: "Head-to-head vs. Zillow",
}

function availableSegments(
  metrics: BacktestMetric[],
  allLabel: string,
  subjects: [number, string][]
): { value: string; label: string }[] {
  const present = new Set(metrics.map((m) => m.segment))
  const named: [string, string][] = [
    ["all", allLabel],
    ...Object.entries(SEGMENT_LABELS),
    ...subjects.map(([id, name]): [string, string] => [`region:${id}`, name]),
  ]
  return named
    .filter(([value]) => present.has(value))
    .map(([value, label]) => ({ value, label }))
}
