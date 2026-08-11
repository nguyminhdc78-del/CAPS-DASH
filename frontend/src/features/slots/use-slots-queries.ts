import { useQuery } from '@tanstack/react-query'

import { api } from '@/core/api/api-client'
import { queryKeys } from '@/core/api/query-keys'
import type { SlotListFilters } from '@/core/api/query-keys'
import { MAX_PAGE_SIZE } from '@/core/constants/ui-constants'
import type { SlotState } from '@/shared/components/state-tag'

/** Mirrors `SlotResponse` in backend/caps_dash/api/schemas/slot_schemas.py. */
export interface SlotRecord {
  id: number
  camera_id: number
  code: string
  floor: string
  current_state: SlotState
  state_since: string | null
  is_active: boolean
}

interface SlotPage {
  items: SlotRecord[]
  total: number
  limit: number
  offset: number
}

/**
 * One floor/state/camera-scoped fetch of the whole page.
 *
 * `slots-page.tsx` only ever varies `floor` here - state and camera are
 * filtered client-side against this same fetch (see that file's comment) so
 * flipping those two controls never re-triggers a network round trip, and
 * the count strip and the grid/table always agree because they read the
 * exact same query result. `limit` is fixed at the server's own cap
 * (`MAX_PAGE_SIZE` mirrors `pagination.MAX_LIMIT`): a floor is not expected
 * to exceed it, and if it ever does, that is itself worth surfacing rather
 * than silently paginating a security-facing board.
 */
export function useSlotsQuery(filters: SlotListFilters = {}) {
  const search = new URLSearchParams()
  if (filters.floor !== undefined) search.set('floor', filters.floor)
  if (filters.state !== undefined) search.set('state', filters.state)
  if (filters.cameraId !== undefined) search.set('camera_id', String(filters.cameraId))
  search.set('limit', String(MAX_PAGE_SIZE))

  return useQuery({
    queryKey: queryKeys.slots.list(filters),
    queryFn: () => api.get<SlotPage>(`/slots?${search.toString()}`),
  })
}

/** Mirrors `FloorSummary` / `OccupancySummary` in `api/schemas/summary_schemas.py`. */
export interface FloorSummary {
  floor: string
  total: number
  free: number
  occupied: number
  unknown: number
}

export interface OccupancySummary {
  total: number
  free: number
  occupied: number
  unknown: number
  by_floor: FloorSummary[]
  updated_at: string
}

/**
 * `/summary` - the same endpoint the kiosk polls, used here once per page
 * view (default `staleTime`/`refetchOnWindowFocus` from `query-client.ts`
 * apply, no extra polling) purely as the cross-check the count strip needs.
 */
export function useSummaryQuery() {
  return useQuery({
    queryKey: queryKeys.summary(),
    queryFn: () => api.get<OccupancySummary>('/summary'),
  })
}

/** Mirrors `SlotStateChange` in `api/schemas/history_schemas.py`. */
export interface SlotHistoryRow {
  id: number
  slot_id: number
  camera_code: string
  slot_code: string
  floor: string
  previous_state: SlotState
  new_state: SlotState
  changed_at: string
  clock_suspect: boolean
}

interface SlotHistoryPage {
  items: SlotHistoryRow[]
  total: number
  limit: number
  offset: number
}

// `/history`'s date range is mandatory server-side but defaults to the last
// `history_default_span_days` (7) when omitted - too short for "when did
// this rarely-used slot last change". 30 days stays well under the 92-day
// server cap while covering the drawer's actual need: the last 10 rows for
// one slot, not a report.
const SLOT_HISTORY_LOOKBACK_DAYS = 30
const SLOT_HISTORY_ROW_LIMIT = 10

/**
 * Last 10 state changes for one slot, newest first (the endpoint's own
 * order - see `history_routes.py`), for `slot-detail-drawer.tsx`.
 *
 * Deliberately not added to `core/api/query-keys.ts`: that file is shared
 * infrastructure other phases (13's history page) also extend, and this key
 * is drawer-local. It still nests under the `'slots'` prefix so it is swept
 * up by any future `invalidateQueries({ queryKey: queryKeys.slots.all() })`
 * without this file needing to know that happened.
 */
export function useSlotHistoryQuery(slotId: number | null) {
  return useQuery({
    queryKey: ['slots', 'history', slotId] as const,
    queryFn: async () => {
      const until = new Date()
      const since = new Date(until.getTime() - SLOT_HISTORY_LOOKBACK_DAYS * 24 * 60 * 60 * 1000)
      const search = new URLSearchParams({
        slot_id: String(slotId),
        from: since.toISOString(),
        to: until.toISOString(),
        limit: String(SLOT_HISTORY_ROW_LIMIT),
      })
      const page = await api.get<SlotHistoryPage>(`/history?${search.toString()}`)
      return page.items
    },
    enabled: slotId !== null,
  })
}
