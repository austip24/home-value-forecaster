import { Info } from "lucide-react"

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { modelDescription, modelKind, modelLabel } from "@/lib/models"

/** Model label with a tooltip explaining what the model does. */
export function ModelName({ model }: { model: string }) {
  const description = modelDescription(model)
  if (!description) return <>{modelLabel(model)}</>

  return (
    <Tooltip>
      <TooltipTrigger className="inline-flex cursor-help items-center gap-1 rounded-sm text-left underline decoration-muted-foreground/50 decoration-dotted underline-offset-4 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
        {modelLabel(model)}
        <Info aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
      </TooltipTrigger>
      <TooltipContent className="flex-col items-start gap-1 leading-relaxed">
        <span className="font-medium">{modelKind(model)}</span>
        <span>{description}</span>
      </TooltipContent>
    </Tooltip>
  )
}
