import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { api } from '@/core/api/api-client'
import { queryKeys } from '@/core/api/query-keys'

/**
 * Camera/slot lookups that back the filter dropdowns on the history,
 * sessions and statistics pages.
 *
 * These three pages all filter by `camera_code`, `slot_id` and/or `floor`,
 * none of which the reporting endpoints themselves enumerate - `/history`
 * and `/sessions` only accept those as query params, they do not return
 * "here are the valid values". So the dropdowns are populated from the
 * existing `/cameras` and `/slots` lists instead of duplicating that data
 * server-side just for this. `MAX_PAGE_SIZE` is requested (not the default
 * page size) because a filter dropdown missing a camera or slot is a worse
 * failure than an admin page whose default view is one page - see
 * `core/constants/ui-constants.ts`.
 */

const OPTIONS_LIMIT = 200 // MAX_LIMIT in backend/caps_dash/api/pagination.py

interface CameraOption {
  id: number
  code: string
  floor: string
}

interface SlotOption {
  id: number
  code: string
  floor: string
  camera_id: number
}

interface OptionPage<T> {
  items: T[]
  total: number
}

export function useCameraOptionsQuery() {
  return useQuery({
    queryKey: queryKeys.filterOptions.cameras(),
    queryFn: () => api.get<OptionPage<CameraOption>>(`/cameras?limit=${OPTIONS_LIMIT}`),
    staleTime: 60_000,
  })
}

export function useSlotOptionsQuery() {
  return useQuery({
    queryKey: queryKeys.filterOptions.slots(),
    queryFn: () => api.get<OptionPage<SlotOption>>(`/slots?limit=${OPTIONS_LIMIT}`),
    staleTime: 60_000,
  })
}

/** Distinct floors across every slot, sorted - feeds the floor `<Select>`. */
export function useFloorOptions(): string[] {
  const { data } = useSlotOptionsQuery()
  return useMemo(() => {
    const floors = new Set((data?.items ?? []).map((slot) => slot.floor))
    return [...floors].sort((a, b) => a.localeCompare(b))
  }, [data])
}

export type { CameraOption, SlotOption }
