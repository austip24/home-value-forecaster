import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { TREND_TEXT_CLASS } from "@/components/market/trend"
import { cn } from "@/lib/utils"
import { describeStep, formatMonth, formatValue } from "@/lib/series"
import type { SeriesPoint, ValueUnit } from "@/lib/types"

/** Text alternative to the trend chart: newest first, with month-over-month change. */
export function PriceTable({
  points,
  metric,
  unit,
  colorize,
}: {
  points: SeriesPoint[]
  metric: string
  unit: ValueUnit
  /** Color changes green/red; see KpiCards. */
  colorize: boolean
}) {
  const rows = points
    .map((point, i) => {
      const prev = points[i - 1]?.value
      const mom =
        point.value !== null && prev != null
          ? describeStep(prev, point.value, unit)
          : null
      return { ...point, mom }
    })
    .reverse()

  return (
    <div className="h-80 overflow-y-auto rounded-lg border">
      <Table>
        <TableHeader className="sticky top-0 bg-card">
          <TableRow>
            <TableHead>Month</TableHead>
            <TableHead className="text-right">{metric}</TableHead>
            <TableHead className="text-right">MoM</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.date}>
              <TableCell>{formatMonth(row.date)}</TableCell>
              <TableCell className="text-right font-mono tabular-nums">
                {row.value === null ? "—" : formatValue(row.value, unit)}
              </TableCell>
              <TableCell
                className={cn(
                  "text-right font-mono tabular-nums",
                  colorize && TREND_TEXT_CLASS[row.mom?.direction ?? "flat"]
                )}
              >
                {row.mom?.text ?? "—"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
