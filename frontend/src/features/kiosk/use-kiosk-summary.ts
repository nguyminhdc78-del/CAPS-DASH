import { useQuery } from '@tanstack/react-query'

import { api } from '@/core/api/api-client'
import { queryKeys } from '@/core/api/query-keys'
import { KIOSK_POLL_MS } from '@/core/constants/ui-constants'
import type { OccupancySummary } from '@/features/slots/use-slots-queries'

export interface KioskSummaryState {
  /** Last successfully fetched summary, or `null` before the first success. */
  summary: OccupancySummary | null
  /** True while the most recent poll failed - `summary` still holds the
   * last good value regardless. */
  isOffline: boolean
  /** When `summary` was last refreshed, or `null` if never. */
  lastUpdatedAt: Date | null
}

/**
 * Polls `/api/summary` for the lobby display.
 *
 * `refetchIntervalInBackground: true` is the one non-default option: a
 * lobby screen has no tab-visibility concept to pause for, and TanStack
 * Query's normal "stop polling in a background tab" behaviour would freeze
 * the numbers the moment the kiosk's browser chrome loses focus (e.g. a
 * screensaver, or a technician alt-tabbing on the machine driving it).
 *
 * Deliberately does NOT reach for `placeholderData` or a manual ref to hold
 * "the last good value" - `useQuery` already keeps `data` from the last
 * successful fetch when a later fetch fails (it does not null `data` out on
 * error), and `dataUpdatedAt` is the timestamp of that same last success.
 * Reading both together is the entire "keep stale data, know its age"
 * contract; anything more would be a second cache duplicating the first.
 */
export function useKioskSummary(): KioskSummaryState {
  const query = useQuery({
    queryKey: queryKeys.summary(),
    queryFn: () => api.get<OccupancySummary>('/summary'),
    refetchInterval: KIOSK_POLL_MS,
    refetchIntervalInBackground: true,
  })

  return {
    summary: query.data ?? null,
    isOffline: query.isError,
    lastUpdatedAt: query.dataUpdatedAt ? new Date(query.dataUpdatedAt) : null,
  }
}
