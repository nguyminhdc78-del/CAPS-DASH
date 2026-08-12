import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/core/api/api-client'
import { queryKeys } from '@/core/api/query-keys'
import type { CameraListParams } from '@/core/api/query-keys'

/** Mirrors `CameraSourceType` in backend/caps_dash/db/enums.py. */
export type CameraSourceType =
  | 'esp32cam_http'
  | 'esp32cam_stream'
  | 'rtsp'
  | 'image_folder'
  | 'video_file'
  | 'fake'

/** Live counters from the running worker. `null` when no worker is running. */
export interface CameraHealth {
  online: boolean
  frames_ok: number
  frames_failed: number
  fail_streak: number
  errors: number
  process_ms: number
  average_process_ms: number
  viewers: number
}

/** Mirrors `CameraWithHealth` in backend/caps_dash/api/schemas/camera_schemas.py. */
export interface CameraRecord {
  id: number
  code: string
  name: string
  floor: string
  source_type: CameraSourceType
  source_url: string
  poll_interval_s: number
  vote_window: number
  vote_threshold: number
  confidence: number
  is_enabled: boolean
  frame_width: number
  frame_height: number
  last_seen_at: string | null
  last_error: string
  slot_count: number
  health: CameraHealth | null
}

interface CameraPage {
  items: CameraRecord[]
  total: number
  limit: number
  offset: number
}

/** Mirrors `CreateCameraRequest`. */
export interface CreateCameraInput {
  code: string
  name: string
  floor: string
  source_type: CameraSourceType
  source_url: string
  poll_interval_s: number
  vote_window: number
  vote_threshold: number
  confidence: number
  is_enabled: boolean
}

/**
 * Mirrors `UpdateCameraRequest`, minus `code` (immutable after creation, the
 * schema has no such field) and `confidence` (kept off the edit form on
 * purpose - see `camera-form-drawer.tsx` - so tuning it always goes through
 * the no-restart `/runtime` endpoint instead of the full update).
 */
export type UpdateCameraInput = Partial<Omit<CreateCameraInput, 'code' | 'confidence'>>

/** Extra `useQuery` knobs beyond the params baked into the cache key.
 * Kept separate from `CameraListParams` because `refetchInterval`/`enabled`
 * are read-behaviour, not part of what makes two requests "the same page" -
 * folding them into the key would fragment the cache for callers that only
 * differ in how often they poll the identical list (the overview's hero
 * picker and its camera-health strip both do exactly this). */
export interface CameraListOptions {
  refetchInterval?: number
  enabled?: boolean
}

export function useCamerasQuery(params: CameraListParams = {}, options: CameraListOptions = {}) {
  const search = new URLSearchParams()
  if (params.limit !== undefined) search.set('limit', String(params.limit))
  if (params.offset !== undefined) search.set('offset', String(params.offset))
  const query = search.toString()

  return useQuery({
    queryKey: queryKeys.cameras.list(params),
    queryFn: () => api.get<CameraPage>(`/cameras${query ? `?${query}` : ''}`),
    // Spread conditionally, not `refetchInterval: options.refetchInterval`:
    // under `exactOptionalPropertyTypes`, a key present-but-`undefined`
    // is a different type than an absent key, and TanStack's overloads only
    // accept the latter - an always-present key breaks type inference for
    // every caller of this hook, not just the ones passing options.
    ...(options.refetchInterval !== undefined ? { refetchInterval: options.refetchInterval } : {}),
    ...(options.enabled !== undefined ? { enabled: options.enabled } : {}),
  })
}

export function useCreateCameraMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateCameraInput) => api.post<CameraRecord>('/cameras', input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameras.all() })
    },
  })
}

export function useUpdateCameraMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...input }: UpdateCameraInput & { id: number }) =>
      api.patch<CameraRecord>(`/cameras/${id}`, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameras.all() })
    },
  })
}

export function useDeleteCameraMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete(`/cameras/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameras.all() })
    },
  })
}
