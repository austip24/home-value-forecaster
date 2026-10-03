import {
  Calendar1,
  CalendarDays,
  CalendarRange,
  type LucideIcon,
} from "lucide-react"

import { ModelName } from "@/components/forecast/model-name"
import { TREND_TEXT_CLASS } from "@/components/market/trend"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { comparisonRows, findForecast } from "@/lib/forecast"
import { BENCHMARK_MODEL, HORIZONS, modelKind, modelLabel } from "@/lib/models"
import {
  describeStep,
  formatMonth,
  formatSignedPercent,
  formatValue,
  type Direction,
} from "@/lib/series"
import type { RegionForecast } from "@/lib/types"
import { cn } from "@/lib/utils"

type ForecastPanelProps = {
  regionName: string
  forecast: RegionForecast
}

export function ForecastPanel({
  regionName,
  forecast: rf,
}: ForecastPanelProps) {
  const model = rf.featured_model
  const rows = comparisonRows(rf)
  const { unit } = rf
  // Green/red only where rising is good (home values), as in the KPI cards.
  const colorize = unit === "usd"
  const step = (value: number) => describeStep(rf.origin_value, value, unit)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Forecast · {regionName}</CardTitle>
        <CardDescription>
          <ModelName model={model} /> · from the {formatMonth(rf.origin_date)}{" "}
          value of {formatValue(rf.origin_value, unit)}
        </CardDescription>
        <CardAction>
          <Badge variant="outline">{modelKind(model)}</Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {HORIZONS.map((h) => {
            const f = findForecast(rf, model, h)
            const zhvf = findForecast(rf, BENCHMARK_MODEL, h)
            if (!f) {
              return (
                <HorizonTile
                  key={h}
                  symbol={HORIZON_ICON[h]}
                  label={`${h}-month`}
                  value="—"
                  detail="No forecast"
                  colorize={colorize}
                />
              )
            }
            return (
              <HorizonTile
                key={h}
                symbol={HORIZON_ICON[h]}
                label={`${h}-month · ${formatMonth(f.target_date)}`}
                value={formatValue(f.value, unit)}
                change={step(f.value)}
                colorize={colorize}
                detail={
                  f.lower !== null && f.upper !== null
                    ? `80% interval ${formatValue(f.lower, unit)} – ${formatValue(f.upper, unit)}`
                    : "No interval available"
                }
                note={
                  zhvf
                    ? `Zillow: ${formatSignedPercent(zhvf.value / rf.origin_value - 1)}`
                    : undefined
                }
              />
            )
          })}
        </div>

        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">All models</h3>
          <div className="overflow-x-auto rounded-lg border">
            <Table>
              <caption className="sr-only">
                Forecast change from {formatMonth(rf.origin_date)} by model and
                horizon
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
                {rows.map((row) => (
                  <TableRow
                    key={row.model}
                    className={cn(row.model === model && "bg-muted/50")}
                  >
                    <TableCell>
                      <span className="flex items-center gap-2">
                        <ModelName model={row.model} />
                        {row.model === model && (
                          <Badge variant="secondary">Featured</Badge>
                        )}
                        {row.model === BENCHMARK_MODEL && (
                          <Badge variant="outline">Benchmark</Badge>
                        )}
                      </span>
                    </TableCell>
                    {row.cells.map(({ horizon, forecast }) => {
                      const change = forecast ? step(forecast.value) : null
                      return (
                        <TableCell
                          key={horizon}
                          className={cn(
                            "text-right font-mono tabular-nums",
                            colorize &&
                              change &&
                              TREND_TEXT_CLASS[change.direction]
                          )}
                          title={
                            forecast
                              ? formatValue(forecast.value, unit)
                              : undefined
                          }
                        >
                          {change?.text ?? "—"}
                        </TableCell>
                      )
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </CardContent>
      <CardFooter className="border-t py-3 text-xs text-muted-foreground">
        Model {modelLabel(model)} · Origin {formatMonth(rf.origin_date)} · Data
        release {rf.release}
      </CardFooter>
    </Card>
  )
}

// Same time-span icons as the history KPI cards (1-month, 12-month).
const HORIZON_ICON: Record<(typeof HORIZONS)[number], LucideIcon> = {
  1: Calendar1,
  3: CalendarDays,
  12: CalendarRange,
}

function HorizonTile({
  symbol: SymbolIcon,
  label,
  value,
  change,
  colorize,
  detail,
  note,
}: {
  /** Forecast horizon; decorative, since the label says it in words. */
  symbol: LucideIcon
  label: string
  value: string
  change?: { text: string; direction: Direction } | null
  colorize: boolean
  detail: string
  note?: string
}) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border p-4">
      <span className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        {label}
        <SymbolIcon aria-hidden className="size-4 shrink-0" />
      </span>
      <span className="flex items-baseline gap-2">
        <span className="text-2xl font-semibold tabular-nums">{value}</span>
        {change && (
          <span
            className={cn(
              "text-sm font-medium tabular-nums",
              colorize && TREND_TEXT_CLASS[change.direction]
            )}
          >
            {change.text}
          </span>
        )}
      </span>
      <span className="text-xs text-muted-foreground">{detail}</span>
      {note && <span className="text-xs text-muted-foreground">{note}</span>}
    </div>
  )
}
