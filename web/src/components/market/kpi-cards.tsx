import {
  ArrowDownRight,
  ArrowUpRight,
  Calendar1,
  CalendarRange,
  ChartLine,
  Gauge,
  House,
  Minus,
  Percent,
  type LucideIcon,
} from "lucide-react"

import {
  Card,
  CardAction,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { TREND_TEXT_CLASS } from "@/components/market/trend"
import { cn } from "@/lib/utils"
import {
  describeChange,
  formatMonth,
  formatValue,
  type Change,
  type SeriesKpis,
} from "@/lib/series"
import type { ValueUnit } from "@/lib/types"

type KpiCardsProps = {
  kpis: SeriesKpis
  rangeLabel: string
  /** Label for the latest-value card, e.g. "Typical home value". */
  latestLabel: string
  unit: ValueUnit
  /**
   * Color changes green/red. Only meaningful when rising is good (home values);
   * for rates like unemployment, direction is shown by the arrow alone.
   */
  colorize: boolean
}

const LATEST_ICON: Record<ValueUnit, LucideIcon> = {
  usd: House,
  percent: Percent,
  index: Gauge,
}

export function KpiCards({
  kpis,
  rangeLabel,
  latestLabel,
  unit,
  colorize,
}: KpiCardsProps) {
  const { latest, rangeHigh, rangeChange } = kpis
  const offHigh =
    rangeHigh.date !== latest.date
      ? describeChange(
          {
            absolute: latest.value - rangeHigh.value,
            percent: (latest.value - rangeHigh.value) / rangeHigh.value,
            from: rangeHigh,
          },
          unit
        ).value
      : null
  const changeProps = { unit, colorize }

  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
      <Kpi
        label={latestLabel}
        symbol={LATEST_ICON[unit]}
        value={formatValue(latest.value, unit)}
        detail={`As of ${formatMonth(latest.date)}`}
      />
      <ChangeKpi
        label="1-month change"
        symbol={Calendar1}
        change={kpis.monthChange}
        {...changeProps}
      />
      <ChangeKpi
        label="12-month change"
        symbol={CalendarRange}
        change={kpis.yearChange}
        {...changeProps}
      />
      <ChangeKpi
        label={`Change · ${rangeLabel}`}
        symbol={ChartLine}
        change={rangeChange}
        {...changeProps}
        note={
          offHigh === null
            ? "At range high"
            : `${offHigh} vs. ${formatMonth(rangeHigh.date)} high`
        }
      />
    </div>
  )
}

function Kpi({
  label,
  symbol: SymbolIcon,
  value,
  detail,
  note,
  icon,
  valueClassName,
}: {
  label: string
  /** What the KPI measures; decorative, since the label says it in words. */
  symbol: LucideIcon
  value: string
  detail: string
  note?: string
  icon?: React.ReactNode
  valueClassName?: string
}) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardAction>
          <SymbolIcon aria-hidden className="size-4 text-muted-foreground" />
        </CardAction>
        <CardTitle
          className={cn(
            "flex items-center gap-1 text-xl font-semibold tabular-nums sm:text-2xl",
            valueClassName
          )}
        >
          {icon}
          {value}
        </CardTitle>
        <p className="text-xs text-muted-foreground">{detail}</p>
        {note && <p className="text-xs text-muted-foreground">{note}</p>}
      </CardHeader>
    </Card>
  )
}

function ChangeKpi({
  label,
  symbol,
  change,
  note,
  unit,
  colorize,
}: {
  label: string
  symbol: LucideIcon
  change: Change | null
  note?: string
  unit: ValueUnit
  colorize: boolean
}) {
  if (!change) {
    return (
      <Kpi
        label={label}
        symbol={symbol}
        value="—"
        detail="Not enough history"
      />
    )
  }

  const { value, direction, detail } = describeChange(change, unit)
  const { Icon, label: directionLabel } = DIRECTION_ICON[direction]

  return (
    <Kpi
      label={label}
      symbol={symbol}
      value={value}
      icon={<Icon aria-label={directionLabel} className="size-5" />}
      valueClassName={colorize ? TREND_TEXT_CLASS[direction] : undefined}
      detail={detail}
      note={note}
    />
  )
}

const DIRECTION_ICON = {
  up: { Icon: ArrowUpRight, label: "Up" },
  down: { Icon: ArrowDownRight, label: "Down" },
  flat: { Icon: Minus, label: "Unchanged" },
} as const
