"use client"

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
} from "recharts"

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { mergeChartRows, type ForecastOverlay } from "@/lib/forecast"
import { modelLabel } from "@/lib/models"
import {
  formatAxisValue,
  formatMonth,
  formatShortMonth,
  formatValue,
  type RangeId,
} from "@/lib/series"
import type { SeriesPoint, ValueUnit } from "@/lib/types"

type PriceTrendChartProps = {
  points: SeriesPoint[]
  range: RangeId
  metric: string
  unit?: ValueUnit
  forecast?: ForecastOverlay | null
}

export function PriceTrendChart({
  points,
  range,
  metric,
  unit = "usd",
  forecast,
}: PriceTrendChartProps) {
  const config = {
    value: { label: metric, color: "var(--chart-1)" },
    forecast: {
      label: forecast ? `${modelLabel(forecast.model)} forecast` : "Forecast",
      color: "var(--chart-2)",
    },
    band: { label: "80% interval", color: "var(--chart-2)" },
    benchmark: { label: modelLabel("zhvf"), color: "var(--chart-3)" },
  } satisfies ChartConfig

  const rows = mergeChartRows(points, forecast ?? null)
  const hasBand = rows.some((r) => r.band)
  const hasBenchmark = rows.some((r) => r.benchmark != null)

  // Long ranges label one tick per year (January) so year labels never repeat.
  const shortRange = range === "1y" || range === "3y"
  const ticks = shortRange
    ? undefined
    : rows.filter((p) => p.date.slice(5, 7) === "01").map((p) => p.date)
  const tickFormatter = (date: string) =>
    shortRange ? formatShortMonth(date) : date.slice(0, 4)

  return (
    <div className="flex flex-col gap-3">
      <ChartContainer config={config} className="aspect-auto h-80 w-full">
        <ComposedChart
          data={rows}
          margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
        >
          <defs>
            <linearGradient id="fill-value" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="0%"
                stopColor="var(--color-value)"
                stopOpacity={0.18}
              />
              <stop
                offset="100%"
                stopColor="var(--color-value)"
                stopOpacity={0}
              />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} />
          <XAxis
            dataKey="date"
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            minTickGap={40}
            ticks={ticks}
            tickFormatter={tickFormatter}
          />
          <YAxis
            width={64}
            tickLine={false}
            axisLine={false}
            tickMargin={4}
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => formatAxisValue(v, unit)}
          />
          <ChartTooltip
            cursor={{ strokeWidth: 1 }}
            content={
              <ChartTooltipContent
                labelFormatter={(_, payload) => {
                  const date: unknown = payload[0]?.payload?.date
                  return typeof date === "string" ? formatMonth(date) : null
                }}
                formatter={(value, name) => {
                  const key = String(name) as keyof typeof config
                  const formatted = Array.isArray(value)
                    ? `${formatValue(Number(value[0]), unit)} – ${formatValue(Number(value[1]), unit)}`
                    : formatValue(Number(value), unit)
                  return (
                    <div className="flex w-full items-center gap-2">
                      <span
                        className="h-0.5 w-3 shrink-0 rounded-full"
                        style={{ background: `var(--color-${key})` }}
                      />
                      <span className="font-mono font-medium text-foreground tabular-nums">
                        {formatted}
                      </span>
                      <span className="text-muted-foreground">
                        {config[key]?.label ?? name}
                      </span>
                    </div>
                  )
                }}
              />
            }
          />
          <Area
            dataKey="value"
            type="monotone"
            stroke="var(--color-value)"
            strokeWidth={2}
            fill="url(#fill-value)"
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--background)" }}
            isAnimationActive={false}
          />
          {hasBand && (
            <Area
              dataKey="band"
              type="linear"
              stroke="none"
              fill="var(--color-band)"
              fillOpacity={0.15}
              connectNulls
              activeDot={false}
              isAnimationActive={false}
            />
          )}
          {forecast && (
            <Line
              dataKey="forecast"
              type="linear"
              stroke="var(--color-forecast)"
              strokeWidth={2}
              strokeDasharray="5 4"
              connectNulls
              dot={{ r: 3, fill: "var(--color-forecast)", strokeWidth: 0 }}
              isAnimationActive={false}
            />
          )}
          {hasBenchmark && (
            <Line
              dataKey="benchmark"
              type="linear"
              stroke="var(--color-benchmark)"
              strokeWidth={1.5}
              strokeDasharray="2 3"
              connectNulls
              dot={{ r: 2.5, fill: "var(--color-benchmark)", strokeWidth: 0 }}
              isAnimationActive={false}
            />
          )}
        </ComposedChart>
      </ChartContainer>

      {forecast && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <LegendItem color="var(--chart-1)" label={metric} />
          <LegendItem
            color="var(--chart-2)"
            label={config.forecast.label}
            dashed
          />
          {hasBand && (
            <LegendItem color="var(--chart-2)" label="80% interval" swatch />
          )}
          {hasBenchmark && (
            <LegendItem
              color="var(--chart-3)"
              label={config.benchmark.label}
              dashed
            />
          )}
        </ul>
      )}
    </div>
  )
}

function LegendItem({
  color,
  label,
  dashed,
  swatch,
}: {
  color: string
  label: string
  dashed?: boolean
  swatch?: boolean
}) {
  return (
    <li className="flex items-center gap-1.5">
      {swatch ? (
        <span
          className="size-3 rounded-sm opacity-30"
          style={{ background: color }}
        />
      ) : (
        <span
          className="w-4 border-t-2"
          style={{
            borderColor: color,
            borderStyle: dashed ? "dashed" : "solid",
          }}
        />
      )}
      {label}
    </li>
  )
}
