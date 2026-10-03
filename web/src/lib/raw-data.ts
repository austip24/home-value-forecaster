// Server-only reader for raw provider snapshots in data/raw/.
// Stand-in for Postgres until the forecaster's publish step is wired up;
// queries.ts is the only caller, so swapping the backend touches one file.

import { readdir, readFile, stat } from "node:fs/promises"
import path from "node:path"

import { findFredSeries } from "@/lib/fred"
import type { ProviderId, RegionOption, SeriesPoint } from "@/lib/types"

// Defaults to the bundle in web/data/ written by `forecaster export-web`, which
// next.config.ts ships with the server function (outputFileTracingIncludes). The
// turbopackIgnore hints stop the bundler from tracing these dynamic paths itself.
const RAW_DATA_DIR =
  process.env.RAW_DATA_DIR ??
  path.join(/*turbopackIgnore: true*/ process.cwd(), "data", "raw")

const rawPath = (...segments: string[]) =>
  path.join(/*turbopackIgnore: true*/ RAW_DATA_DIR, ...segments)

const RELEASE_PATTERN = /^\d{4}-\d{2}$/

type ProviderSource = {
  dir: string
  /** Matches the snapshot file inside a release folder. Null = no reader yet. */
  filePattern: RegExp | null
}

const SOURCES: Record<ProviderId, ProviderSource> = {
  zillow: { dir: "zillow", filePattern: /^zhvi_metro_allhomes_sm_sa.*\.csv$/ },
  redfin: { dir: "redfin", filePattern: null },
  // FRED has one file per series; any of them marks a usable release.
  fred: { dir: "fred", filePattern: /\.csv$/ },
}

export type ParsedDataset = {
  release: string
  regions: RegionOption[]
  series: Map<number, SeriesPoint[]>
}

/** Latest release folder that contains a readable snapshot, newest first. */
export async function findLatestSnapshot(
  provider: ProviderId
): Promise<{ release: string; file: string } | null> {
  const { dir, filePattern } = SOURCES[provider]
  if (!filePattern) return null

  const releases = (await safeReaddir(rawPath(dir)))
    .filter((name) => RELEASE_PATTERN.test(name))
    .sort()
    .reverse()

  for (const release of releases) {
    const files = await safeReaddir(rawPath(dir, release))
    const match = files.find((f) => filePattern.test(f))
    if (match) return { release, file: rawPath(dir, release, match) }
  }
  return null
}

const cache = new Map<
  string,
  { mtimeMs: number; data: Promise<ParsedDataset> }
>()

/**
 * Parses the latest wide (Zillow-format) snapshot for a provider, memoized by
 * file path + mtime. FRED is long-format; read it with loadFredSeries.
 */
export async function loadDataset(
  provider: ProviderId
): Promise<ParsedDataset | null> {
  if (provider === "fred") return null
  const snapshot = await findLatestSnapshot(provider)
  if (!snapshot) return null

  const { mtimeMs } = await stat(snapshot.file)
  const cached = cache.get(snapshot.file)
  if (cached && cached.mtimeMs === mtimeMs) return cached.data

  const data = readFile(snapshot.file, "utf8").then((text) =>
    parseZillowWide(text, snapshot.release)
  )
  cache.set(snapshot.file, { mtimeMs, data })
  return data
}

const ID_COLUMNS = [
  "RegionID",
  "SizeRank",
  "RegionName",
  "RegionType",
  "StateName",
] as const

/**
 * Zillow research CSVs are wide: identifier columns followed by one column per
 * month-end date. Returns regions plus a per-region series keyed by RegionID.
 */
export function parseZillowWide(text: string, release: string): ParsedDataset {
  const rows = parseCsv(text)
  const header = rows[0]
  if (!header) throw new Error("Empty Zillow CSV")

  const col = Object.fromEntries(
    ID_COLUMNS.map((name) => {
      const index = header.indexOf(name)
      if (index === -1) throw new Error(`Zillow CSV missing column ${name}`)
      return [name, index]
    })
  ) as Record<(typeof ID_COLUMNS)[number], number>

  const dateColumns = header
    .map((name, index) => ({ name, index }))
    .filter(({ name }) => /^\d{4}-\d{2}-\d{2}$/.test(name))

  const regions: RegionOption[] = []
  const series = new Map<number, SeriesPoint[]>()

  for (const row of rows.slice(1)) {
    const regionId = Number(row[col.RegionID])
    if (!Number.isFinite(regionId)) continue

    const points = dateColumns.map(({ name, index }) => {
      const raw = row[index]
      const value = raw ? Number(raw) : NaN
      return { date: name, value: Number.isFinite(value) ? value : null }
    })
    if (points.every((p) => p.value === null)) continue

    const sizeRank = Number(row[col.SizeRank])
    regions.push({
      region_id: regionId,
      region_name: row[col.RegionName] ?? String(regionId),
      state: row[col.StateName] || null,
      size_rank: Number.isFinite(sizeRank) ? sizeRank : null,
      region_type: row[col.RegionType] ?? "",
    })
    series.set(regionId, points)
  }

  regions.sort(
    (a, b) =>
      (a.size_rank ?? Number.MAX_SAFE_INTEGER) -
      (b.size_rank ?? Number.MAX_SAFE_INTEGER)
  )
  return { release, regions, series }
}

/** Minimal RFC 4180 parser: quoted fields, escaped quotes, CRLF. */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let field = ""
  let inQuotes = false

  for (let i = 0; i < text.length; i++) {
    const char = text[i]
    if (inQuotes) {
      if (char === '"' && text[i + 1] === '"') {
        field += '"'
        i++
      } else if (char === '"') {
        inQuotes = false
      } else {
        field += char
      }
    } else if (char === '"') {
      inQuotes = true
    } else if (char === ",") {
      row.push(field)
      field = ""
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && text[i + 1] === "\n") i++
      row.push(field)
      rows.push(row)
      row = []
      field = ""
    } else {
      field += char
    }
  }
  if (field !== "" || row.length > 0) {
    row.push(field)
    rows.push(row)
  }
  return rows
}

const fredCache = new Map<
  string,
  { mtimeMs: number; data: Promise<SeriesPoint[]> }
>()

/** One FRED series from the latest snapshot, as monthly means at month-end. */
export async function loadFredSeries(
  seriesId: string
): Promise<{ release: string; points: SeriesPoint[] } | null> {
  const series = findFredSeries(seriesId)
  const snapshot = await findLatestSnapshot("fred")
  if (!series || !snapshot) return null

  const files = await safeReaddir(rawPath("fred", snapshot.release))
  const match = files.find((f) => series.filePattern.test(f))
  if (!match) return null

  const file = rawPath("fred", snapshot.release, match)
  const { mtimeMs } = await stat(file)
  const cached = fredCache.get(file)
  if (cached && cached.mtimeMs === mtimeMs) {
    return { release: snapshot.release, points: await cached.data }
  }

  const data = readFile(file, "utf8").then(parseFredMonthly)
  fredCache.set(file, { mtimeMs, data })
  return { release: snapshot.release, points: await data }
}

/**
 * FRED snapshot CSV (`date,value,...`, daily/weekly/monthly) -> monthly means
 * keyed by month-end, matching the forecaster's fred_to_monthly.
 */
export function parseFredMonthly(text: string): SeriesPoint[] {
  const rows = parseCsv(text)
  const header = rows[0] ?? []
  const dateCol = header.indexOf("date")
  const valueCol = header.indexOf("value")
  if (dateCol === -1 || valueCol === -1)
    throw new Error("FRED CSV missing columns")

  const months = new Map<string, { total: number; n: number }>()
  for (const row of rows.slice(1)) {
    const date = row[dateCol]
    const value = Number(row[valueCol])
    if (!date || row[valueCol] === "" || !Number.isFinite(value)) continue
    const month = date.slice(0, 7)
    const m = months.get(month) ?? { total: 0, n: 0 }
    months.set(month, { total: m.total + value, n: m.n + 1 })
  }

  return [...months.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, { total, n }]) => ({
      date: monthEnd(month),
      value: total / n,
    }))
}

/** "2024-02" -> "2024-02-29". */
function monthEnd(month: string): string {
  const [y, m] = month.split("-").map(Number)
  const day = new Date(Date.UTC(y, m, 0)).getUTCDate()
  return `${month}-${String(day).padStart(2, "0")}`
}

async function safeReaddir(dir: string): Promise<string[]> {
  try {
    return await readdir(dir)
  } catch {
    return []
  }
}
