import { useCallback, useEffect, useRef, useState } from 'react'

const FPS_WINDOW_MS = 5000
/** Publish at most twice a second - a readout does not need to repaint at frame rate. */
const TICK_MS = 500

export interface StreamMetricsSummary {
  /** Frames actually displayed in the last 5s, not frames merely received. */
  fps: number
  /** Time since the last frame was displayed, or null before the first one. */
  lastFrameAgeMs: number | null
}

/**
 * Rolling FPS + frame age, computed from timestamps recorded via
 * `recordFrame()` and republished on a fixed timer - never on every frame,
 * so a fast camera does not turn the stats strip into its own source of
 * re-renders.
 */
export function useStreamMetrics(): { metrics: StreamMetricsSummary; recordFrame: () => void } {
  const timestampsRef = useRef<number[]>([])
  const lastFrameAtRef = useRef<number | null>(null)
  const [metrics, setMetrics] = useState<StreamMetricsSummary>({ fps: 0, lastFrameAgeMs: null })

  const recordFrame = useCallback(() => {
    const now = Date.now()
    lastFrameAtRef.current = now
    timestampsRef.current.push(now)
  }, [])

  useEffect(() => {
    const timer = setInterval(() => {
      const now = Date.now()
      const cutoff = now - FPS_WINDOW_MS
      timestampsRef.current = timestampsRef.current.filter((timestamp) => timestamp >= cutoff)
      const fps = timestampsRef.current.length / (FPS_WINDOW_MS / 1000)
      const lastFrameAgeMs =
        lastFrameAtRef.current === null ? null : now - lastFrameAtRef.current
      setMetrics({ fps, lastFrameAgeMs })
    }, TICK_MS)
    return () => clearInterval(timer)
  }, [])

  return { metrics, recordFrame }
}
