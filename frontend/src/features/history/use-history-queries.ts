import { useQuery } from '@tanstack/react-query'

import { api } from '@/core/api/api-client'
import { authTokenStore } from '@/core/api/auth-token-store'
import { apiErrorFromResponse } from '@/core/api/api-error'
import { queryKeys } from '@/core/api/query-keys'
import type { HistoryRangeFilters } from '@/core/api/query-keys'
import { refreshAccessToken } from '@/core/api/refresh-single-flight'
import { DEFAULT_PAGE_SIZE } from '@/core/constants/ui-constants'

/** Mirrors `SlotStateChange` in backend/caps_dash/api/schemas/history_schemas.py. */
export interface SlotStateChangeRecord {
  id: number
  slot_id: number
  camera_code: string
  slot_code: string
  floor: string
  previous_state: string
  new_state: string
  changed_at: string
  clock_suspect: boolean
}

interface HistoryPage {
  items: SlotStateChangeRecord[]
  total: number
  limit: number
  offset: number
}

/**
 * Mirrors `Settings.history_default_span_days` / `history_max_span_days` in
 * backend/caps_dash/config/settings.py. Neither is exposed over the API, so
 * these are duplicated here to seed the filter bar's initial range and to
 * soft-cap the date picker; the server remains the actual authority and
 * still rejects an over-wide range with `RANGE_TOO_WIDE` regardless of what
 * the picker allowed (e.g. a bookmarked URL with hand-edited params).
 */
export const HISTORY_DEFAULT_SPAN_DAYS = 7
export const HISTORY_MAX_SPAN_DAYS = 92

export function buildRangeQuery(filters: HistoryRangeFilters): string {
  const search = new URLSearchParams()
  if (filters.from) search.set('from', filters.from)
  if (filters.to) search.set('to', filters.to)
  if (filters.slotId !== undefined) search.set('slot_id', String(filters.slotId))
  if (filters.cameraCode) search.set('camera_code', filters.cameraCode)
  if (filters.floor) search.set('floor', filters.floor)
  search.set('limit', String(filters.limit ?? DEFAULT_PAGE_SIZE))
  search.set('offset', String(filters.offset ?? 0))
  return search.toString()
}

export function useHistoryQuery(filters: HistoryRangeFilters) {
  return useQuery({
    queryKey: queryKeys.history.list(filters),
    queryFn: () => api.get<HistoryPage>(`/history?${buildRangeQuery(filters)}`),
    // Keeps the previous page's rows on screen while the next page loads,
    // instead of flashing the table empty on every click of the pager.
    placeholderData: (previous) => previous,
  })
}

/**
 * Streams `/exports/history.csv` to disk.
 *
 * Not `api.get<T>()` - that helper always parses the body as JSON. Auth and
 * the 401-refresh-retry dance are reproduced here at the fetch layer, same
 * pattern as `features/roi-editor/use-camera-snapshot.ts`. `response.blob()`
 * lets the browser stream the body straight into its own blob storage
 * rather than this code accumulating chunks in a JS array first - the part
 * that matters for "do not buffer unnecessarily" on a 100k-row export.
 */
export async function downloadHistoryCsv(
  filters: Omit<HistoryRangeFilters, 'limit' | 'offset'>,
  retryOnUnauthorized = true,
): Promise<Blob> {
  const search = new URLSearchParams()
  if (filters.from) search.set('from', filters.from)
  if (filters.to) search.set('to', filters.to)
  if (filters.slotId !== undefined) search.set('slot_id', String(filters.slotId))
  if (filters.cameraCode) search.set('camera_code', filters.cameraCode)
  if (filters.floor) search.set('floor', filters.floor)

  const headers = new Headers()
  const token = authTokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(`/api/exports/history.csv?${search.toString()}`, {
    headers,
    credentials: 'same-origin',
  })

  if (response.status === 401 && retryOnUnauthorized) {
    if (await refreshAccessToken()) return downloadHistoryCsv(filters, false)
    throw await apiErrorFromResponse(response)
  }
  if (!response.ok) throw await apiErrorFromResponse(response)
  return response.blob()
}
