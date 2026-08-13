import { useQuery } from '@tanstack/react-query'

import { api } from '@/core/api/api-client'
import { queryKeys } from '@/core/api/query-keys'
import { MIN_PLATE_QUERY_LENGTH } from '@/features/plates/use-plate-search-query'

// Re-exported rather than redeclared: the backend enforces one minimum
// (`plate_search_service.py`'s `MIN_QUERY_LENGTH`), shared by the staff and
// public routes alike, and `use-plate-search-query.ts` already mirrors it.
export { MIN_PLATE_QUERY_LENGTH }

/** Mirrors `PublicPlateMatch` in backend/caps_dash/api/schemas/plate_schemas.py -
 * exactly four fields. Deliberately narrower than the staff `PlateMatch`
 * (`use-plate-search-query.ts`): no `camera_id`/`camera_code` (camera
 * topology), no `slot_state` or `confidence` (both leak how sure the system
 * is that a car is still there), no `plate_width_px`. An anonymous kiosk
 * visitor gets the bay and nothing that lets them judge or trace the read. */
export interface PublicPlateMatch {
  plate: string
  slot_code: string
  floor: string
  read_at: string
}

export interface PublicPlateSearchResult {
  /** The normalised form the server actually searched for. */
  query: string
  matches: PublicPlateMatch[]
}

/**
 * A public, partial-match plate search - the unauthenticated counterpart of
 * `usePlateSearchQuery`, against `/api/public/plates/search`.
 *
 * Deliberately not a debounced search-as-you-type, same as the staff
 * version: every call to this endpoint is written to the anonymous audit
 * log, because a plate identifies a vehicle and through it a person - typing
 * `30H83231` as-you-type would file eight audit entries for one question.
 * `submitted` therefore changes on Enter or the button, not on keystroke
 * (see `kiosk-plate-search.tsx`).
 */
export function useKioskPlateSearch(submitted: string) {
  const trimmed = submitted.trim()

  return useQuery({
    queryKey: queryKeys.publicKiosk.plateSearch(trimmed),
    queryFn: () => {
      const search = new URLSearchParams({ q: trimmed })
      return api.get<PublicPlateSearchResult>(`/public/plates/search?${search.toString()}`)
    },
    enabled: trimmed.length >= MIN_PLATE_QUERY_LENGTH,
    // A car does not move between two identical searches a minute apart, and
    // a re-fetch would file another audit entry for a question already asked.
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  })
}
