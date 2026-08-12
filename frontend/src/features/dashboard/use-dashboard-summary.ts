import { useQuery } from '@tanstack/react-query'

import { api } from '@/core/api/api-client'
import { queryKeys } from '@/core/api/query-keys'
import { SUMMARY_POLL_MS } from '@/core/constants/ui-constants'
import type { OccupancySummary } from '@/features/slots/use-slots-queries'

export interface DashboardSummaryState {
  summary: OccupancySummary | null
  isLoading: boolean
  isError: boolean
  /** When `summary` was last refreshed, or `null` before the first success. */
  lastUpdatedAt: Date | null
}

/**
 * Polls `/summary` for the overview page - the one endpoint every role can
 * call, so both the resident and staff layouts build on this single hook.
 *
 * Mirrors `use-kiosk-summary.ts`'s "keep the last good value on a failed
 * poll" behaviour (TanStack already does this: `data` is not nulled out by a
 * failing refetch) without that hook's `refetchIntervalInBackground` - this
 * is a normal app tab a person navigates away from, not a screen bolted to a
 * lobby wall, so pausing polls while the tab is hidden (TanStack's default)
 * is the right call here.
 */
export function useDashboardSummary(): DashboardSummaryState {
  const query = useQuery({
    queryKey: queryKeys.summary(),
    queryFn: () => api.get<OccupancySummary>('/summary'),
    refetchInterval: SUMMARY_POLL_MS,
  })

  return {
    summary: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    lastUpdatedAt: query.dataUpdatedAt ? new Date(query.dataUpdatedAt) : null,
  }
}
