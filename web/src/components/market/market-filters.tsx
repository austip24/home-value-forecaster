"use client"

import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "@/components/ui/combobox"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { RANGES, isRangeId, type RangeId } from "@/lib/series"
import type {
  Provider,
  ProviderId,
  RegionOption,
  SeriesOption,
} from "@/lib/types"

type MarketFiltersProps = {
  range: RangeId
  onRangeChange: (range: RangeId) => void
  regions: RegionOption[]
  region: RegionOption
  onRegionChange: (regionId: number) => void
  providers: Provider[]
  provider: ProviderId
  onProviderChange: (provider: ProviderId) => void
  /** Series to choose between, for providers that offer several (FRED). */
  seriesOptions: SeriesOption[] | null
  seriesId: string | null
  onSeriesChange: (seriesId: string) => void
}

export function MarketFilters({
  range,
  onRangeChange,
  regions,
  region,
  onRegionChange,
  providers,
  provider,
  onProviderChange,
  seriesOptions,
  seriesId,
  onSeriesChange,
}: MarketFiltersProps) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <FilterField label="Date range">
        <Tabs
          value={range}
          onValueChange={(value) => {
            if (isRangeId(value)) onRangeChange(value)
          }}
        >
          <TabsList aria-label="Date range">
            {RANGES.map((r) => (
              <TabsTrigger key={r.id} value={r.id} className="px-3">
                {r.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </FilterField>

      {/* Location is always available; providers with several series (FRED)
          also get a Series picker. */}
      <FilterField label="Location">
        <Combobox
          items={regions}
          value={region}
          onValueChange={(next) => {
            if (next) onRegionChange(next.region_id)
          }}
          itemToStringLabel={(r) => r.region_name}
          isItemEqualToValue={(a, b) => a.region_id === b.region_id}
        >
          <ComboboxInput
            placeholder={
              regions.length > 1 ? "Search metros…" : "Search locations…"
            }
            aria-label="Location"
            className="w-72"
          />
          <ComboboxContent>
            <ComboboxEmpty>No matching locations.</ComboboxEmpty>
            <ComboboxList>
              {(r: RegionOption) => (
                <ComboboxItem key={r.region_id} value={r}>
                  <span className="truncate">{r.region_name}</span>
                  <span className="ml-auto text-xs text-muted-foreground tabular-nums">
                    {r.region_type === "country"
                      ? "National"
                      : `#${r.size_rank}`}
                  </span>
                </ComboboxItem>
              )}
            </ComboboxList>
          </ComboboxContent>
        </Combobox>
      </FilterField>

      {seriesOptions && (
        <FilterField label="Series">
          <Select
            value={seriesId}
            onValueChange={(value) => {
              if (typeof value === "string") onSeriesChange(value)
            }}
            items={seriesOptions.map((o) => ({ value: o.id, label: o.label }))}
          >
            <SelectTrigger aria-label="Series" className="w-72">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {seriesOptions.map((o) => (
                <SelectItem key={o.id} value={o.id} disabled={o.disabled}>
                  {o.label}
                  {o.note && (
                    <span className="text-xs text-muted-foreground">
                      {o.note}
                    </span>
                  )}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterField>
      )}

      <FilterField label="Data provider">
        <Select
          value={provider}
          onValueChange={(value) => {
            const next = providers.find((p) => p.id === value)
            if (next?.release) onProviderChange(next.id)
          }}
          items={providers.map((p) => ({ value: p.id, label: p.label }))}
        >
          <SelectTrigger aria-label="Data provider" className="w-52">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {providers.map((p) => (
              <SelectItem key={p.id} value={p.id} disabled={!p.release}>
                {p.label}
                <span className="text-xs text-muted-foreground">
                  {p.release ?? "Coming soon"}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FilterField>
    </div>
  )
}

function FilterField({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </div>
  )
}
