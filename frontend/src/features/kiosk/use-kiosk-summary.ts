import { useQuery } from '@tanstack/react-query'

import { ApiError } from '@/core/api/api-error'
import { api } from '@/core/api/api-client'
import { queryKeys } from '@/core/api/query-keys'
import { KIOSK_POLL_MS } from '@/core/constants/ui-constants'
import type { OccupancySummary } from '@/features/slots/use-slots-queries'

/** Mirrors `PublicOccupancySummary` in backend/caps_dash/api/schemas/plate_schemas.py.
 * `counts` nests the same `OccupancySummary` shape the authenticated
 * `/summary` endpoint returns - the public surface adds two fields beside it
 * rather than reshaping it, so the floor list (`by_floor`) is read the same
 * way in both places. */
interface PublicOccupancySummary {
  counts: OccupancySummary
  /** FREE slot codes only, capped at 40/floor server-side. Never occupied
   * codes - an empty bay holds no car, an occupied one identifies a vehicle. */
  free_codes_by_floor: Record<string, string[]>
  /** Rides on this response rather than a second endpoint: the page already
   * polls this one, and a second request/query key for one boolean would be
   * a second thing that can drift out of sync with the first. */
  plate_search_enabled: boolean
}

export interface KioskSummaryState {
  /** Last successfully fetched counts, or `null` before the first success. */
  summary: OccupancySummary | null
  /** FREE codes per floor, `{}` before the first success. */
  freeCodesByFloor: Record<string, string[]>
  /** Whether the plate search box should render at all - absent, not
   * disabled, when false (see `kiosk-page.tsx`). */
  plateSearchEnabled: boolean
  /** True while the most recent poll failed for a reason other than the
   * kiosk being disabled - `summary` still holds the last good value
   * regardless. */
  isOffline: boolean
  /** True when the server 404s with `PUBLIC_KIOSK_DISABLED` - the operator
   * has not opted into the public surface. Distinct from `isOffline`: this
   * is not a transient failure, so it gets its own notice, not a banner. */
  isDisabled: boolean
  /** When `summary` was last refreshed, or `null` if never. */
  lastUpdatedAt: Date | null
}

function isKioskDisabledError(error: unknown): boolean {
  return error instanceof ApiError && error.code === 'PUBLIC_KIOSK_DISABLED'
}

/**
 * Polls `/api/public/summary` for the lobby display - the unauthenticated
 * counterpart of `/summary`. Two flags gate what this returns server-side
 * (`PUBLIC_KIOSK_ENABLED`, `PLATE_READING_ENABLED`); this hook only reads
 * the result, it does not itself decide what is safe to show.
 *
 * `refetchIntervalInBackground: true` is the one non-default option: a
 * lobby screen has no tab-visibility concept to pause for, and TanStack
 * Query's normal "stop polling in a background tab" behaviour would freeze
 * the numbers the moment the kiosk's browser chrome loses focus (e.g. a
 * screensaver, or a technician alt-tabbing on the machine driving it).
 *
 * `refetchInterval` stops once `isDisabled` is true: a disabled feature will
 * not enable itself mid-session, so continuing to poll every 3s against a
 * guaranteed 404 would only spam the network and console for no benefit.
 *
 * Deliberately does NOT fall back to the authenticated `/summary` on
 * failure - that would be two code paths serving one screen, and would run
 * the 401 refresh dance (`api-client.ts:38-47`) on a page that has no
 * session to refresh. A deployment upgrades by setting
 * `PUBLIC_KIOSK_ENABLED=true` (see the deployment guide), not by silently
 * falling back to a different, resident-tier endpoint.
 */
export function useKioskSummary(): KioskSummaryState {
  const query = useQuery({
    queryKey: queryKeys.publicKiosk.summary(),
    queryFn: () => api.get<PublicOccupancySummary>('/public/summary'),
    refetchInterval: (q) => (isKioskDisabledError(q.state.error) ? false : KIOSK_POLL_MS),
    refetchIntervalInBackground: true,
  })

  const isDisabled = isKioskDisabledError(query.error)

  return {
    summary: query.data?.counts ?? null,
    freeCodesByFloor: query.data?.free_codes_by_floor ?? {},
    plateSearchEnabled: query.data?.plate_search_enabled ?? false,
    isOffline: query.isError && !isDisabled,
    isDisabled,
    lastUpdatedAt: query.dataUpdatedAt ? new Date(query.dataUpdatedAt) : null,
  }
}
