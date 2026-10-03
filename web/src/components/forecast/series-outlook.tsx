import Link from "next/link"

import { ModelName } from "@/components/forecast/model-name"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { findForecast } from "@/lib/forecast"
import type { FredSeries } from "@/lib/fred"
import { describeStep, formatValue } from "@/lib/series"
import type { RegionForecast } from "@/lib/types"
import { cn } from "@/lib/utils"

type SeriesOutlookProps = {
  model: string
  items: { series: FredSeries; forecast: RegionForecast }[]
  /** The series currently shown, highlighted in the list. */
  activeSeriesId: string | null
}

/**
 * Projected 12-month change for every FRED series: the macro counterpart of
 * the metro movers list, in the same layout.
 */
export function SeriesOutlook({
  model,
  items,
  activeSeriesId,
}: SeriesOutlookProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Projected 12-month changes</CardTitle>
        <CardDescription>
          <ModelName model={model} /> forecast, all FRED series.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="flex flex-col divide-y rounded-lg border">
          {items.map(({ series, forecast }) => {
            const year = findForecast(forecast, model, 12)
            const change = year
              ? describeStep(forecast.origin_value, year.value, series.unit)
              : null
            return (
              <li key={series.id}>
                <Link
                  href={`?provider=fred&series=${series.id}`}
                  scroll={false}
                  aria-current={
                    series.id === activeSeriesId ? "page" : undefined
                  }
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 text-sm hover:bg-muted/50",
                    series.id === activeSeriesId && "bg-muted/50"
                  )}
                >
                  <span className="min-w-0 flex-1 truncate">
                    {series.label}
                  </span>
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {formatValue(forecast.origin_value, series.unit)} →{" "}
                    {year ? formatValue(year.value, series.unit) : "—"}
                  </span>
                  <span className="w-20 text-right font-mono tabular-nums">
                    {change?.text ?? "—"}
                  </span>
                </Link>
              </li>
            )
          })}
        </ol>
      </CardContent>
    </Card>
  )
}
