import { useQuery } from '@tanstack/react-query'

import { api } from '@/core/api/api-client'
import { queryKeys } from '@/core/api/query-keys'

/** Mirrors `PlateMatchResponse` in backend/caps_dash/api/schemas/plate_schemas.py. */
export interface PlateMatch {
  plate: string
  slot_code: string
  floor: string
  camera_id: number
  camera_code: string
  slot_state: string
  read_at: string
  confidence: number
  plate_width_px: number
}

export interface PlateSearchResult {
  /** The normalised form the server actually searched for. */
  query: string
  matches: PlateMatch[]
}

/**
 * Mirrors `MIN_QUERY_LENGTH` in
 * backend/caps_dash/services/plate_search_service.py. Duplicated here so the
 * UI can say why it is not searching yet instead of firing a request that
 * comes back empty by rule; the server remains the authority.
 */
export const MIN_PLATE_QUERY_LENGTH = 3

/**
 * A plate search, run only when the guard asks for one.
 *
 * Deliberately not a debounced search-as-you-type. Every call to this
 * endpoint is written to the audit log, because a plate identifies a vehicle
 * and through it a person - typing `30H83231` as-you-type would file eight
 * audit entries for one question and bury the record of who really looked for
 * what. `submitted` therefore changes on Enter or the button, not on
 * keystroke.
 */
export function usePlateSearchQuery(submitted: string, includeVacated: boolean) {
  const trimmed = submitted.trim()

  return useQuery({
    queryKey: queryKeys.plates.search(trimmed, includeVacated),
    queryFn: () => {
      const search = new URLSearchParams({ q: trimmed })
      if (includeVacated) search.set('include_vacated', 'true')
      return api.get<PlateSearchResult>(`/plates/search?${search.toString()}`)
    },
    enabled: trimmed.length >= MIN_PLATE_QUERY_LENGTH,
    // A car does not move between two identical searches a minute apart, and
    // a re-fetch would file another audit entry for a question already asked.
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  })
}
