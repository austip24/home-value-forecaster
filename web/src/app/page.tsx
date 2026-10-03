import { ForecastPanel } from "@/components/forecast/forecast-panel"
import { ModelPerformance } from "@/components/forecast/model-performance"
import { Movers } from "@/components/forecast/movers"
import { QuickInsights } from "@/components/forecast/quick-insights"
import { SeriesOutlook } from "@/components/forecast/series-outlook"
import { MarketDashboard } from "@/components/market/market-dashboard"
import { buildOverlay } from "@/lib/forecast"
import { FRED_REGION, findFredSeries } from "@/lib/fred"
import { buyTimingInsight, trendInsight } from "@/lib/insights"
import {
  getFredOutlook,
  getModelPerformance,
  getMortgageRate,
  getMovers,
  getProviders,
  getRegionForecast,
  getRegionSeries,
  getRegions,
  isProviderId,
} from "@/lib/queries"
import { DEFAULT_RANGE, isRangeId } from "@/lib/series"
import type { DatasetId } from "@/lib/types"

const MOVERS_MAX_SIZE_RANK = 100

type SearchParams = Promise<Record<string, string | string[] | undefined>>

export default async function Page({
  searchParams,
}: {
  searchParams: SearchParams
}) {
  const params = await searchParams
  const providers = await getProviders()
  const available = providers.filter((p) => p.release !== null)

  const requested = params.provider
  const provider =
    available.find((p) => isProviderId(requested) && p.id === requested) ??
    available[0]

  if (!provider) {
    return (
      <Shell>
        <EmptyState>
          No raw data found. Run{" "}
          <code className="font-mono">poetry run forecaster ingest</code> to
          download a snapshot into <code className="font-mono">data/raw/</code>.
        </EmptyState>
      </Shell>
    )
  }

  const regions = await getRegions(provider.id)
  const requestedRegion = Number(params.region)
  const region =
    regions.find((r) => r.region_id === requestedRegion) ??
    regions.find((r) => r.region_type === "country") ??
    regions[0]
  const series = region
    ? await getRegionSeries(
        provider.id,
        region.region_id,
        typeof params.series === "string" ? params.series : undefined
      )
    : null
  const range = isRangeId(params.range) ? params.range : DEFAULT_RANGE

  if (!series) {
    return (
      <Shell>
        <EmptyState>
          No regions found in the {provider.label} snapshot.
        </EmptyState>
      </Shell>
    )
  }

  // Zillow metros and FRED series share one forecasting pipeline and one
  // layout; only labels, questions, and the movers/outlook card differ.
  const isZillow = series.provider === "zillow"
  const isFred = series.provider === "fred"
  // FRED at a metro location means that metro's unemployment rate.
  const isFredMetro =
    isFred && series.region.region_id !== FRED_REGION.region_id
  const fredSeries =
    isFred && !isFredMetro ? findFredSeries(series.series_id) : undefined
  const dataset: DatasetId | null = isZillow
    ? "zillow"
    : isFredMetro
      ? "fred_metro"
      : isFred
        ? "fred"
        : null
  const subjectId = fredSeries?.key ?? series.region.region_id
  const national = regions.find((r) => r.region_type === "country")
  const isNational = isZillow && national?.region_id === series.region.region_id

  const [forecast, performance, movers, outlook, nationalSeries, mortgage] =
    dataset
      ? await Promise.all([
          getRegionForecast(subjectId, dataset),
          getModelPerformance(dataset),
          isZillow || isFredMetro
            ? getMovers({
                dataset: isFredMetro ? "fred_metro" : "zillow",
                maxSizeRank: MOVERS_MAX_SIZE_RANK,
              })
            : null,
          isFred && !isFredMetro ? getFredOutlook() : null,
          // What the trend insight compares against: U.S. home values for a
          // Zillow metro, the national unemployment rate for a FRED metro.
          isZillow && national && !isNational
            ? getRegionSeries("zillow", national.region_id)
            : isFredMetro
              ? getRegionSeries("fred", FRED_REGION.region_id, "unemployment")
              : null,
          isZillow ? getMortgageRate() : null,
        ])
      : [null, null, null, null, null, null]

  const subjectName = fredSeries
    ? fredSeries.label
    : isNational
      ? "the U.S."
      : series.region.region_name
  const questions = isFredMetro
    ? {
        buy: "",
        trend: `How is unemployment in ${subjectName} trending?`,
        footnote:
          "Based on projected metro unemployment (BLS data via FRED, smoothed seasonally adjusted). Not financial advice.",
      }
    : fredSeries
      ? {
          buy: "When is the best time to lock in a mortgage rate?",
          trend: `How is ${fredSeries.subject} trending?`,
          footnote:
            fredSeries.id === "mortgage_rate"
              ? "Based on the projected national average 30-year rate (Freddie Mac via FRED). Your rate depends on your credit, loan, and lender. Not financial advice."
              : "Based on projected national FRED data, not local conditions. Not financial advice.",
        }
      : {
          buy: `When is the best time to buy in ${subjectName}?`,
          trend: `How is ${subjectName} trending?`,
          footnote: mortgage
            ? "Based on projected home values, with national mortgage rates (Freddie Mac via FRED) as context. Doesn't account for your finances or local listings. Not financial advice."
            : "Based on projected home values only. Doesn't account for mortgage rates, your finances, or local listings. Not financial advice.",
        }
  // Buy timing applies to home values and to mortgage rates (when to lock);
  // unemployment and CPI have no buying decision attached.
  const showBuyTiming = isZillow || fredSeries?.id === "mortgage_rate"

  return (
    <Shell>
      <MarketDashboard
        // Remount on navigation so local range state resets with the new URL.
        key={`${series.provider}-${series.region.region_id}-${series.series_id ?? ""}`}
        providers={providers}
        regions={regions}
        series={series}
        initialRange={range}
        forecast={forecast ? buildOverlay(forecast) : null}
      />
      {forecast && (
        <QuickInsights
          model={forecast.featured_model}
          originDate={forecast.origin_date}
          buyQuestion={questions.buy}
          buyTiming={
            showBuyTiming ? buyTimingInsight(forecast, mortgage) : null
          }
          trendQuestion={questions.trend}
          trend={trendInsight({
            regionName: subjectName,
            regionId: subjectId,
            points: series.points,
            nationalPoints: nationalSeries?.points ?? null,
            forecast,
            metrics: performance?.metrics ?? [],
          })}
          footnote={questions.footnote}
        />
      )}
      {dataset &&
        (forecast ? (
          <ForecastPanel
            regionName={
              fredSeries
                ? fredSeries.label
                : isFredMetro
                  ? `Unemployment rate · ${series.region.region_name}`
                  : series.region.region_name
            }
            forecast={forecast}
          />
        ) : (
          <EmptyState>
            No forecast for {subjectName}. Run the forecaster (
            <code className="font-mono">
              poetry run forecaster forecast --dataset {dataset}
            </code>
            ) to write forecasts to{" "}
            <code className="font-mono">data/processed/&lt;release&gt;/</code>.
          </EmptyState>
        ))}
      {(movers || outlook || performance) && (
        <div className="grid gap-6 lg:grid-cols-2">
          {movers && (
            <Movers
              model={movers.model}
              gainers={movers.gainers}
              decliners={movers.decliners}
              maxSizeRank={MOVERS_MAX_SIZE_RANK}
              provider={series.provider}
              unit={movers.unit}
              subject={isZillow ? "home values" : "unemployment"}
            />
          )}
          {outlook && (
            <SeriesOutlook
              model={outlook.model}
              items={outlook.items}
              activeSeriesId={series.series_id}
            />
          )}
          {performance && dataset && (
            <ModelPerformance
              performance={performance}
              regionId={subjectId}
              regionName={subjectName}
              featuredModel={
                forecast?.featured_model ??
                movers?.model ??
                outlook?.model ??
                null
              }
              dataset={dataset}
            />
          )}
        </div>
      )}
    </Shell>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex min-h-svh w-full max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold tracking-tight">
          Home Value Forecaster
        </h1>
        <p className="text-sm text-muted-foreground">
          Metro-level home value trends and forecasts.
        </p>
      </header>
      <main className="flex flex-col gap-6">{children}</main>
      <footer className="mt-auto border-t pt-4 text-xs text-muted-foreground">
        Home value data from{" "}
        <a
          href="https://www.zillow.com/research/data/"
          className="underline underline-offset-2 hover:text-foreground"
        >
          Zillow Research
        </a>
        . Zillow Home Value Index (ZHVI) © Zillow, Inc. Mortgage rate,
        unemployment, and CPI data from{" "}
        <a
          href="https://fred.stlouisfed.org/"
          className="underline underline-offset-2 hover:text-foreground"
        >
          FRED
        </a>
        , Federal Reserve Bank of St. Louis.
      </footer>
    </div>
  )
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
      {children}
    </p>
  )
}
