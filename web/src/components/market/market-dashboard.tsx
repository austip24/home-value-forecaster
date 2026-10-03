"use client"

import { useMemo, useState, useTransition } from "react"
import { useRouter } from "next/navigation"

import { PriceTrendChart } from "@/components/charts/price-trend-chart"
import { KpiCards } from "@/components/market/kpi-cards"
import { MarketFilters } from "@/components/market/market-filters"
import { PriceTable } from "@/components/market/price-table"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { ForecastOverlay } from "@/lib/forecast"
import { FRED_REGION, FRED_SERIES } from "@/lib/fred"
import { cn } from "@/lib/utils"
import {
  RANGES,
  computeKpis,
  filterByRange,
  formatMonth,
  type RangeId,
} from "@/lib/series"
import type { Provider, RegionOption, RegionSeries } from "@/lib/types"

type MarketDashboardProps = {
  providers: Provider[]
  regions: RegionOption[]
  series: RegionSeries
  initialRange: RangeId
  forecast?: ForecastOverlay | null
}

export function MarketDashboard({
  providers,
  regions,
  series,
  initialRange,
  forecast,
}: MarketDashboardProps) {
  const router = useRouter()
  const [isPending, startTransition] = useTransition()
  const [range, setRange] = useState(initialRange)
  const [view, setView] = useState<"chart" | "table">("chart")

  const provider = providers.find((p) => p.id === series.provider)
  // Green/red only reads correctly when rising is good, as with home values.
  const colorize = series.unit === "usd"
  // FRED metros only have unemployment; mortgage rates and CPI are national.
  const isMetro = series.region.region_id !== FRED_REGION.region_id
  const seriesOptions =
    series.provider === "fred"
      ? FRED_SERIES.map((s) => {
          const nationalOnly = isMetro && s.id !== "unemployment"
          return {
            id: s.id,
            label: s.label,
            disabled: nationalOnly,
            note: nationalOnly ? "National only" : undefined,
          }
        })
      : null
  const rangeLabel = RANGES.find((r) => r.id === range)?.label ?? range
  const rangePoints = useMemo(
    () => filterByRange(series.points, range),
    [series.points, range]
  )
  const kpis = useMemo(
    () => computeKpis(series.points, rangePoints),
    [series.points, rangePoints]
  )

  // Provider and region change the data, so they round-trip to the server.
  // Range only slices what's already loaded, so it updates the URL in place.
  const navigate = (params: Record<string, string>) => {
    const search = new URLSearchParams(window.location.search)
    for (const [key, value] of Object.entries(params)) search.set(key, value)
    startTransition(() =>
      router.push(`?${search.toString()}`, { scroll: false })
    )
  }

  const changeRange = (next: RangeId) => {
    setRange(next)
    const search = new URLSearchParams(window.location.search)
    search.set("range", next)
    window.history.replaceState(null, "", `?${search.toString()}`)
  }

  return (
    <div className="flex flex-col gap-6">
      <MarketFilters
        range={range}
        onRangeChange={changeRange}
        regions={regions}
        region={series.region}
        onRegionChange={(id) => navigate({ region: String(id) })}
        providers={providers}
        provider={series.provider}
        onProviderChange={(id) => navigate({ provider: id })}
        seriesOptions={seriesOptions}
        seriesId={series.series_id}
        onSeriesChange={(id) => navigate({ series: id })}
      />

      <div
        aria-busy={isPending}
        className={cn(
          "flex flex-col gap-6 transition-opacity",
          isPending && "opacity-60"
        )}
      >
        {kpis && (
          <KpiCards
            kpis={kpis}
            rangeLabel={rangeLabel}
            latestLabel={
              series.unit === "usd" ? "Typical home value" : series.metric
            }
            unit={series.unit}
            colorize={colorize}
          />
        )}

        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {series.metric} · {series.region.region_name}
            </CardTitle>
            <CardDescription>{series.description}</CardDescription>
            <CardAction>
              <Tabs
                value={view}
                onValueChange={(value) =>
                  setView(value === "table" ? "table" : "chart")
                }
              >
                <TabsList aria-label="View">
                  <TabsTrigger value="chart" className="px-3">
                    Chart
                  </TabsTrigger>
                  <TabsTrigger value="table" className="px-3">
                    Table
                  </TabsTrigger>
                </TabsList>
              </Tabs>
            </CardAction>
          </CardHeader>
          <CardContent>
            {rangePoints.length === 0 ? (
              <p className="flex h-80 items-center justify-center text-muted-foreground">
                No observations for this location.
              </p>
            ) : view === "chart" ? (
              <PriceTrendChart
                points={rangePoints}
                range={range}
                metric={series.metric}
                unit={series.unit}
                forecast={forecast}
              />
            ) : (
              <PriceTable
                points={rangePoints}
                metric={series.metric}
                unit={series.unit}
                colorize={colorize}
              />
            )}
          </CardContent>
          <CardFooter className="border-t py-3 text-xs text-muted-foreground">
            Source: {provider?.label} · Release {series.release}
            {kpis && ` · Latest observation ${formatMonth(kpis.latest.date)}`}
          </CardFooter>
        </Card>
      </div>
    </div>
  )
}
