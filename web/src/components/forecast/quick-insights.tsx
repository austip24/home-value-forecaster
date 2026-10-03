import { ArrowDownRight, ArrowUpRight, Lightbulb, Minus } from "lucide-react"

import { ModelName } from "@/components/forecast/model-name"
import { TREND_TEXT_CLASS } from "@/components/market/trend"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import type { Insight } from "@/lib/insights"
import { formatMonth, type Direction } from "@/lib/series"
import { cn } from "@/lib/utils"

type QuickInsightsProps = {
  model: string
  originDate: string
  /** e.g. "When is the best time to buy in Phoenix, AZ?" */
  buyQuestion: string
  buyTiming: Insight | null
  /** e.g. "How is Phoenix, AZ trending?" */
  trendQuestion: string
  trend: Insight | null
  /** What the insights are based on, and their limits. */
  footnote: string
}

export function QuickInsights({
  model,
  originDate,
  buyQuestion,
  buyTiming,
  trendQuestion,
  trend,
  footnote,
}: QuickInsightsProps) {
  if (!buyTiming && !trend) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Lightbulb aria-hidden className="size-5 shrink-0" />
          Quick insights
        </CardTitle>
        <CardDescription>
          From the <ModelName model={model} /> forecast made with data through{" "}
          {formatMonth(originDate)}.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6 md:grid-cols-2">
        {buyTiming && (
          <InsightBlock question={buyQuestion} insight={buyTiming} />
        )}
        {trend && <InsightBlock question={trendQuestion} insight={trend} />}
      </CardContent>
      <CardFooter className="border-t py-3 text-xs text-muted-foreground">
        {footnote}
      </CardFooter>
    </Card>
  )
}

const TONE_ICON: Record<Direction, { Icon: typeof Minus; label: string }> = {
  up: { Icon: ArrowUpRight, label: "Prices rising" },
  down: { Icon: ArrowDownRight, label: "Prices falling" },
  flat: { Icon: Minus, label: "Prices flat" },
}

function InsightBlock({
  question,
  insight,
}: {
  question: string
  insight: Insight
}) {
  const { Icon, label } = TONE_ICON[insight.tone]
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm text-muted-foreground">{question}</h3>
      <p className="flex items-start gap-1.5 font-medium">
        <Icon
          aria-label={label}
          className={cn(
            "mt-0.5 size-4 shrink-0",
            TREND_TEXT_CLASS[insight.tone]
          )}
        />
        {insight.verdict}
      </p>
      <ul className="flex list-disc flex-col gap-1.5 pl-5 text-sm text-muted-foreground">
        {insight.points.map((point) => (
          <li key={point}>{point}</li>
        ))}
      </ul>
    </section>
  )
}
