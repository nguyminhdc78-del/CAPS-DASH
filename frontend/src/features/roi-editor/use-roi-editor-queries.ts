import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/core/api/api-client'
import { queryKeys } from '@/core/api/query-keys'
import type { SlotMapPayload } from './slot-map-payload'

/** Mirrors `SlotMapEntry`/`SlotMapResponse` in
 * backend/caps_dash/api/schemas/camera_schemas.py. */
export interface SlotMapDto {
  camera_id: number
  src_frame_width: number
  src_frame_height: number
  slots: { code: string; floor: string; polygon: { points: [number, number][] } }[]
}

/**
 * Local query key, not added to `core/api/query-keys.ts`: that file is
 * outside this phase's file ownership. Kept here, named and exported, so a
 * later phase that needs the same key does not have to guess the shape.
 */
export const slotMapQueryKey = (cameraId: number) => ['cameras', 'slot-map', cameraId] as const

export function useSlotMapQuery(cameraId: number) {
  return useQuery({
    queryKey: slotMapQueryKey(cameraId),
    queryFn: () => api.get<SlotMapDto>(`/cameras/${cameraId}/slot-map`),
  })
}

export function useSaveSlotMapMutation(cameraId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: SlotMapPayload) => api.put<SlotMapDto>(`/cameras/${cameraId}/slot-map`, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: slotMapQueryKey(cameraId) })
      // The camera's slot_count and the global slot list both read stale
      // until these refresh too.
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameras.all() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.slots.all() })
    },
  })
}
