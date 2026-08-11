import { Slider, Space, Typography } from 'antd'
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import { api } from '@/core/api/api-client'
import {
  CAMERA_CONFIDENCE_DEBOUNCE_MS,
  CAMERA_CONFIDENCE_MAX,
  CAMERA_CONFIDENCE_MIN,
  CAMERA_CONFIDENCE_STEP,
} from '@/core/constants/ui-constants'
import { useDebouncedValue } from '@/shared/hooks/use-debounced-value'

/**
 * Live confidence tuning for one camera, via `PATCH /cameras/{id}/runtime`.
 *
 * Three mechanisms work together: the slider always tracks the pointer
 * (`displayValue`); only the debounced value ever reaches the network, so
 * dragging cannot flood the API; and an in-flight guard queues at most one
 * more request behind the one in progress rather than firing overlapping
 * PATCHes. A failed request rolls the display back to the last value the
 * server actually confirmed - showing a confidence the camera never adopted
 * would be worse than showing nothing changed.
 */
export function CameraConfidenceSlider({
  cameraId,
  value,
}: {
  cameraId: number
  value: number
}): ReactNode {
  const [displayValue, setDisplayValue] = useState(value)
  const debounced = useDebouncedValue(displayValue, CAMERA_CONFIDENCE_DEBOUNCE_MS)
  const inFlight = useRef(false)
  const lastConfirmed = useRef(value)
  const pending = useRef<number | null>(null)

  // The server value can change from elsewhere (another admin, a refetch);
  // adopt it whenever this slider is not mid-edit.
  useEffect(() => {
    if (!inFlight.current) {
      setDisplayValue(value)
      lastConfirmed.current = value
    }
  }, [value])

  useEffect(() => {
    if (debounced === lastConfirmed.current) return
    if (inFlight.current) {
      pending.current = debounced
      return
    }
    sendConfidence(debounced)
    // sendConfidence is stable across renders (defined inline below, closes
    // only over refs and cameraId); re-running on debounced is the point.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced, cameraId])

  function sendConfidence(next: number): void {
    inFlight.current = true
    api
      .patch<{ confidence: number }>(`/cameras/${cameraId}/runtime`, { confidence: next })
      .then(() => {
        lastConfirmed.current = next
      })
      .catch(() => {
        setDisplayValue(lastConfirmed.current)
      })
      .finally(() => {
        inFlight.current = false
        if (pending.current !== null) {
          const queued = pending.current
          pending.current = null
          if (queued !== lastConfirmed.current) sendConfidence(queued)
        }
      })
  }

  return (
    <Space direction="vertical" style={{ width: 160 }}>
      <Slider
        min={CAMERA_CONFIDENCE_MIN}
        max={CAMERA_CONFIDENCE_MAX}
        step={CAMERA_CONFIDENCE_STEP}
        value={displayValue}
        onChange={(next) => setDisplayValue(next as number)}
        tooltip={{ formatter: (v) => (v ?? 0).toFixed(2) }}
      />
      <Typography.Text type="secondary">{displayValue.toFixed(2)}</Typography.Text>
    </Space>
  )
}
