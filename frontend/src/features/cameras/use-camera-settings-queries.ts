import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { api } from '@/core/api/api-client'
import { queryKeys } from '@/core/api/query-keys'
import { useDebouncedValue } from '@/shared/hooks/use-debounced-value'

/**
 * Mirrors `CameraSettingsResponse` in
 * backend/caps_dash/api/schemas/camera_schemas.py.
 *
 * `settings` stays an open map on purpose: it is whatever the firmware's
 * `/status` handler reports, and the set of keys grows with the sensor
 * driver. Modelling every field here would make this reject a camera that
 * knows one setting more than this file does.
 */
export interface CameraSettingsRecord {
  camera_id: number
  settings: Record<string, unknown>
  /** Present only after a write - which fields the device accepted. */
  applied: Record<string, boolean> | null
}

/** Mirrors `UpdateCameraSettingsRequest`. Every field optional - only what is sent changes. */
export interface CameraSettingsChanges {
  brightness?: number
  contrast?: number
  saturation?: number
  quality?: number
  framesize?: number
  aec?: number
  agc?: number
  awb?: number
  aec_value?: number
  agc_gain?: number
  hmirror?: number
  vflip?: number
  led?: number
  lock_exposure?: boolean
}

/** Shared by every debounced control on the settings drawer - see
 * `camera-confidence-slider.tsx` for why a single-threaded device needs one. */
export const CAMERA_SETTINGS_DEBOUNCE_MS = 400

/**
 * Reads what the device currently reports.
 *
 * `retry: false`: a camera whose source has no controllable sensor answers
 * 422 every time, and a device that is genuinely unreachable will not become
 * reachable by retrying blindly within the same drawer visit - both render
 * their own state (see `camera-settings-drawer.tsx`) instead of a spinner
 * that keeps hammering a dead endpoint.
 */
export function useCameraSettingsQuery(cameraId: number | null) {
  return useQuery({
    queryKey: queryKeys.cameraSettings.detail(cameraId),
    queryFn: () => api.get<CameraSettingsRecord>(`/cameras/${cameraId}/settings`),
    enabled: cameraId !== null,
    retry: false,
  })
}

/**
 * `cameraId` is nullable so the hook can be called unconditionally (rules of
 * hooks) even before a camera is selected; the mutation itself is only ever
 * triggered from controls that are disabled until a camera is loaded.
 */
export function useUpdateCameraSettingsMutation(cameraId: number | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (changes: CameraSettingsChanges) => {
      if (cameraId === null) throw new Error('No camera selected')
      return api.patch<CameraSettingsRecord>(`/cameras/${cameraId}/settings`, changes)
    },
    onSuccess: () => {
      if (cameraId === null) return
      // Invalidated, not written from the response directly: the service
      // re-reads the device after every write specifically because it may
      // clamp values the request did not ask for, so the next GET is the
      // truth and the PATCH response (kept separately as `applied`, in the
      // caller's mutation state) is only a receipt of what was attempted.
      void queryClient.invalidateQueries({ queryKey: queryKeys.cameraSettings.detail(cameraId) })
    },
  })
}

/** Mirrors `RingTestResponse`. `reverts_within_s` is how long before the
 * camera loop takes the ring back - stated by the server rather than assumed
 * here, so the notice cannot drift from `REFRESH_S`. */
export interface RingTestResult {
  camera_id: number
  slots: string
  reverts_within_s: number
}

/**
 * Lights one pattern on the camera node's LED ring.
 *
 * Deliberately not invalidating anything: nothing is stored, and the camera
 * loop overwrites the ring within seconds. There is no server state for this
 * to have gone stale.
 */
export function useRingTestMutation(cameraId: number | null) {
  return useMutation({
    mutationFn: async (slots: string) => {
      if (cameraId === null) throw new Error('No camera selected')
      return api.post<RingTestResult>(`/cameras/${cameraId}/ring-test`, { slots })
    },
  })
}

/** Shared by every settings control (sliders, switches, exposure lock) so
 * they all commit through the drawer's single mutation instance rather than
 * each opening its own - that instance is what carries `applied` after a
 * write. */
export type MutateSettingsChanges = (
  changes: CameraSettingsChanges,
  callbacks: { onSuccess: () => void; onError: () => void },
) => void

/** The subset of `CameraSettingsChanges` rendered as sliders - kept as its
 * own literal union (rather than `field: string`) so the computed property
 * below type-checks against `CameraSettingsChanges` instead of widening to
 * an index signature. */
export type NumericSettingField = 'brightness' | 'contrast' | 'saturation' | 'quality'

/**
 * One field's slider state: always tracks the pointer, but only a value that
 * has settled for `CAMERA_SETTINGS_DEBOUNCE_MS` reaches the network - every
 * drag step would otherwise be a PATCH to a single-threaded device. Mirrors
 * `camera-confidence-slider.tsx`, generalised over a field name so the four
 * numeric sliders do not each reimplement the same debounce/rollback dance.
 *
 * The in-flight guard queues at most one more value behind a request already
 * running rather than firing overlapping PATCHes; a failed request rolls the
 * display back to the last value the device actually confirmed.
 */
export function useDebouncedSettingField(
  field: NumericSettingField,
  serverValue: number,
  disabled: boolean,
  mutate: MutateSettingsChanges,
): { displayValue: number; setDisplayValue: (value: number) => void } {
  const [displayValue, setDisplayValue] = useState(serverValue)
  const debounced = useDebouncedValue(displayValue, CAMERA_SETTINGS_DEBOUNCE_MS)
  const inFlight = useRef(false)
  const lastConfirmed = useRef(serverValue)
  const pending = useRef<number | null>(null)

  // The server value can change from elsewhere (another admin, a refetch);
  // adopt it whenever this slider is not mid-edit.
  useEffect(() => {
    if (!inFlight.current) {
      setDisplayValue(serverValue)
      lastConfirmed.current = serverValue
    }
  }, [serverValue])

  useEffect(() => {
    if (disabled) return
    if (debounced === lastConfirmed.current) return
    if (inFlight.current) {
      pending.current = debounced
      return
    }
    send(debounced)
    // send is stable across renders (closes only over refs, field and
    // mutate); re-running on debounced/disabled is the point.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced, disabled])

  function send(next: number): void {
    inFlight.current = true
    mutate(
      { [field]: next },
      {
        onSuccess: () => {
          lastConfirmed.current = next
          inFlight.current = false
          flushPending()
        },
        onError: () => {
          setDisplayValue(lastConfirmed.current)
          inFlight.current = false
          flushPending()
        },
      },
    )
  }

  function flushPending(): void {
    if (pending.current === null) return
    const queued = pending.current
    pending.current = null
    if (queued !== lastConfirmed.current) send(queued)
  }

  return { displayValue, setDisplayValue }
}
