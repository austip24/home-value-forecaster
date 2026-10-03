import type { Direction } from "@/lib/series"

/** Rising values read as good, falling as bad; flat stays neutral gray. */
export const TREND_TEXT_CLASS: Record<Direction, string> = {
  up: "text-emerald-600 dark:text-emerald-400",
  down: "text-red-600 dark:text-red-400",
  flat: "text-muted-foreground",
}
