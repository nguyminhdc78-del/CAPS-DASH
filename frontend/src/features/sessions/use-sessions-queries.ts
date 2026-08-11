import { useQuery } from '@tanstack/react-query'

import { api } from '@/core/api/api-client'
import { queryKeys } from '@/core/api/query-keys'
import type { HistoryRangeFilters } from '@/core/api/query-keys'
import { DEFAULT_PAGE_SIZE } from '@/core/constants/ui-constants'

// Sessions render under the `history:` namespace - they are the same subject
// seen two ways, and a separate `sessions.json` would split terms like "slot"
// and "duration" across two files that have to agree.

/** Mirrors `ParkingSessionResponse` in
 * backend/caps_dash/api/schemas/history_schemas.py. */
export interface ParkingSessionRecord {
  slot_id: number
  camera_code: string
  slot_code: string
  floor: string
  started_at: string
  ended_at: string | null
  duration_seconds: number | null
  ongoing: boolean
  clock_suspect: boolean
  had_gap: boolean
}

interface SessionsPage {
  items: ParkingSessionRecord[]
  total: number
  limit: number
  offset: number
}

// `/sessions` accepts `from/to/slot_id/camera_code` only - no `floor` query
// param (see api/routes/history_routes.py::list_sessions) - so `floor` on
// the shared `HistoryRangeFilters` is deliberately not forwarded here.
function buildQuery(filters: HistoryRangeFilters): string {
  const search = new URLSearchParams()
  if (filters.from) search.set('from', filters.from)
  if (filters.to) search.set('to', filters.to)
  if (filters.slotId !== undefined) search.set('slot_id', String(filters.slotId))
  if (filters.cameraCode) search.set('camera_code', filters.cameraCode)
  search.set('limit', String(filters.limit ?? DEFAULT_PAGE_SIZE))
  search.set('offset', String(filters.offset ?? 0))
  return search.toString()
}

export function useSessionsQuery(filters: HistoryRangeFilters) {
  return useQuery({
    queryKey: queryKeys.sessions.list(filters),
    queryFn: () => api.get<SessionsPage>(`/sessions?${buildQuery(filters)}`),
    placeholderData: (previous) => previous,
    // An ongoing session's `duration_seconds` is "elapsed as of the
    // request" on the server, not a live value - refetch periodically so it
    // does not look frozen. The table itself ticks the displayed number
    // between refetches from `started_at` (see `sessions-table.tsx`).
    refetchInterval: 30_000,
  })
}
