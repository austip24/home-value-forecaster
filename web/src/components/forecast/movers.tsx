import Link from "next/link"

import { ModelName } from "@/components/forecast/model-name"
import { TREND_TEXT_CLASS } from "@/components/market/trend"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { describeStep, formatValue } from "@/lib/series"
import type { Mover, ProviderId, ValueUnit } from "@/lib/types"
import { cn } from "@/lib/utils"

type MoversProps = {
  model: string
  gainers: Mover[]
  decliners: Mover[]
  maxSizeRank: number
  /** Provider the rows link to, so a click stays on the same data. */
  provider: ProviderId
  unit: ValueUnit
  /** e.g. "home values" or "unemployment"; shown in the description. */
  subject: string
}

/** Biggest projected 12-month rises and falls among large metros. */
export function Movers({
  model,
  gainers,
  decliners,
  maxSizeRank,
  provider,
  unit,
  subject,
}: MoversProps) {
  // Green/red only where rising is good (home values), as in the KPI cards.
  const colorize = unit === "usd"
  const listProps = { provider, unit, colorize }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Projected 12-month movers</CardTitle>
        <CardDescription>
          <ModelName model={model} /> forecast of {subject}, largest{" "}
          {maxSizeRank} metros.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <MoverList
          title={unit === "usd" ? "Biggest gains" : "Biggest rises"}
          movers={gainers}
          {...listProps}
        />
        <MoverList
          title={unit === "usd" ? "Biggest declines" : "Biggest falls"}
          movers={decliners}
          {...listProps}
        />
      </CardContent>
    </Card>
  )
}

function MoverList({
  title,
  movers,
  provider,
  unit,
  colorize,
}: {
  title: string
  movers: Mover[]
  provider: ProviderId
  unit: ValueUnit
  colorize: boolean
}) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-medium">{title}</h3>
      <ol className="flex flex-col divide-y rounded-lg border">
        {movers.map((m) => {
          const change = describeStep(m.origin_value, m.forecast.value, unit)
          return (
            <li key={m.region.region_id}>
              <Link
                href={`?provider=${provider}&region=${m.region.region_id}`}
                scroll={false}
                className="flex items-center gap-3 px-3 py-2 text-sm hover:bg-muted/50"
              >
                <span className="min-w-0 flex-1 truncate">
                  {m.region.region_name}
                </span>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {formatValue(m.forecast.value, unit)}
                </span>
                <span
                  className={cn(
                    "w-20 text-right font-mono tabular-nums",
                    colorize && change && TREND_TEXT_CLASS[change.direction]
                  )}
                >
                  {change?.text ?? "—"}
                </span>
              </Link>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
