import { useEffect, useRef, useState } from 'react'

import { CameraStreamManager } from './camera-stream-manager'
import type { StreamStatus } from './camera-stream-manager'
import { useStreamMetrics } from './use-stream-metrics'
import type { StreamMetricsSummary } from './use-stream-metrics'
import type { FrameHeader } from './frame-header-types'

export interface StreamError {
  /** A close reason ("forbidden", "too_many_viewers", ...) or a local code
   *  ("refresh_failed"). Never a raw exception message - see
   *  stream-close-reason-messages.ts for how this becomes user-facing text. */
  code: string
}

export interface CameraStreamState {
  status: StreamStatus
  header: FrameHeader | null
  jpegUrl: string | null
  error: StreamError | null
  metrics: StreamMetricsSummary
  /** Manual retry, e.g. for a "too many viewers" close the manager will not auto-retry. */
  reconnect: () => void
}

/**
 * Owns one camera's live socket for the lifetime of the mount.
 *
 * All actual connection state lives in a `CameraStreamManager` created fresh
 * inside the effect; this hook only forwards its callbacks into React state.
 * That split is what makes the StrictMode double-invoke safe without any
 * hook-specific gymnastics: the effect's cleanup calls `dispose()` on exactly
 * the manager that effect run created, and the next run creates a new one.
 *
 * `cameraId === null` means "not resolved yet" (e.g. still looking up the
 * camera by its URL code) - no socket opens until it is a real id.
 */
export function useCameraStream(cameraId: number | null): CameraStreamState {
  const [status, setStatus] = useState<StreamStatus>('connecting')
  const [header, setHeader] = useState<FrameHeader | null>(null)
  const [jpegUrl, setJpegUrl] = useState<string | null>(null)
  const [error, setError] = useState<StreamError | null>(null)
  const { metrics, recordFrame } = useStreamMetrics()

  const managerRef = useRef<CameraStreamManager | null>(null)

  useEffect(() => {
    if (cameraId === null) return undefined

    const manager = new CameraStreamManager(cameraId, {
      onStatus: setStatus,
      onFrame: (nextHeader) => {
        setHeader(nextHeader)
        recordFrame()
      },
      onJpegUrl: setJpegUrl,
      onError: setError,
    })
    managerRef.current = manager
    manager.start()

    return () => {
      manager.dispose()
      managerRef.current = null
    }
  }, [cameraId, recordFrame])

  const reconnect = (): void => {
    setError(null)
    managerRef.current?.reconnectNow()
  }

  return { status, header, jpegUrl, error, metrics, reconnect }
}
