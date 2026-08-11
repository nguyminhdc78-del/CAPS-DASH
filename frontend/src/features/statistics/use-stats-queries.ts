import { useQueries, useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'

import { api } from '@/core/api/api-client'
import { queryKeys } from '@/core/api/query-keys'

/** Mirrors `HourlyStatResponse` in backend/caps_dash/api/schemas/stats_schemas.py.
 * Seconds, not percentages - see that schema's docstring for why: a caller
 * can re-aggregate hours into a day without the raw history back, but only
 * if durations (not a pre-divided percentage) are what it stores. */
export interface HourlyStatRecord {
  scope_type: string
  scope_key: string
  hour_start: string
  occupied_seconds: number
  free_seconds: number
  unknown_seconds: number
  change_count: number
  peak_occupied: number
  slot_count: number
  clock_suspect: boolean
}

interface HourlyStatsPage {
  items: HourlyStatRecord[]
  total: number
  limit: number
  offset: number
}

export interface StatsRange {
  from: string
  to: string
}

const PAGE_LIMIT = 200 // MAX_LIMIT in backend/caps_dash/api/pagination.py
// 92 days (the server's history_max_span_days) x 24h = 2208 hourly rows at
// most for one scope; this comfortably covers that with headroom rather
// than looping forever against a misbehaving server.
const MAX_PAGES = 15

/** Fetches every page of `/stats/hourly` for one scope and concatenates
 * them - the chart layer needs the whole range at once, pagination is a
 * server-side memory guard, not something a chart should reason about. */
async function fetchAllHourlyStats(
  scopeType: string,
  scopeKey: string,
  range: StatsRange,
): Promise<HourlyStatRecord[]> {
  const items: HourlyStatRecord[] = []
  let offset = 0
  for (let pageIndex = 0; pageIndex < MAX_PAGES; pageIndex += 1) {
    const search = new URLSearchParams({
      scope_type: scopeType,
      scope_key: scopeKey,
      from: range.from,
      to: range.to,
      limit: String(PAGE_LIMIT),
      offset: String(offset),
    })
    const page = await api.get<HourlyStatsPage>(`/stats/hourly?${search.toString()}`)
    items.push(...page.items)
    offset += page.items.length
    if (page.items.length === 0 || offset >= page.total) break
  }
  return items
}

export function useHourlyStatsQuery(scopeType: string, scopeKey: string, range: StatsRange) {
  return useQuery({
    queryKey: queryKeys.stats.hourly({ scopeType, scopeKey, from: range.from, to: range.to }),
    queryFn: () => fetchAllHourlyStats(scopeType, scopeKey, range),
  })
}

/** One query per floor, run in parallel - `/stats/hourly` filters on a
 * single exact `scope_key`, so there is no "all floors" request to make. */
export function useFloorHourlyStatsQueries(floors: string[], range: StatsRange) {
  return useQueries({
    queries: floors.map((floor) => ({
      queryKey: queryKeys.stats.hourly({ scopeType: 'floor', scopeKey: floor, from: range.from, to: range.to }),
      queryFn: () => fetchAllHourlyStats('floor', floor, range),
    })),
  })
}

function occupancyPercent(row: HourlyStatRecord): number {
  const total = row.occupied_seconds + row.free_seconds + row.unknown_seconds
  return total > 0 ? (row.occupied_seconds / total) * 100 : 0
}

/** Chronological occupancy series for the line chart. Pure and exported so
 * it is unit-testable without mounting Recharts. */
export function toOccupancySeries(rows: HourlyStatRecord[]): { hour: string; occupiedPercent: number }[] {
  return [...rows]
    .sort((a, b) => a.hour_start.localeCompare(b.hour_start))
    .map((row) => ({ hour: row.hour_start, occupiedPercent: occupancyPercent(row) }))
}

/** Average occupancy per hour-of-day (0-23) across the whole range - reveals
 * which hours tend to be busiest regardless of which calendar day. */
export function toPeakHoursSeries(rows: HourlyStatRecord[]): { hourOfDay: number; occupiedPercent: number }[] {
  const sums = Array.from<number>({ length: 24 }).fill(0)
  const counts = Array.from<number>({ length: 24 }).fill(0)
  for (const row of rows) {
    const hourOfDay = dayjs(row.hour_start).hour()
    sums[hourOfDay] = (sums[hourOfDay] ?? 0) + occupancyPercent(row)
    counts[hourOfDay] = (counts[hourOfDay] ?? 0) + 1
  }
  return sums.map((sum, hourOfDay) => ({
    hourOfDay,
    occupiedPercent: counts[hourOfDay] ? sum / (counts[hourOfDay] ?? 1) : 0,
  }))
}

/** One utilisation percentage per floor, summed across the whole range. */
export function toFloorUtilisation(
  floors: string[],
  rowsByFloor: HourlyStatRecord[][],
): { floor: string; utilisationPercent: number }[] {
  return floors.map((floor, index) => {
    const rows = rowsByFloor[index] ?? []
    const occupied = rows.reduce((sum, row) => sum + row.occupied_seconds, 0)
    const total = rows.reduce((sum, row) => sum + row.occupied_seconds + row.free_seconds + row.unknown_seconds, 0)
    return { floor, utilisationPercent: total > 0 ? (occupied / total) * 100 : 0 }
  })
}
