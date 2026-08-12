import { useEffect, useRef, useState } from 'react'

import type { FrameHeader } from '@/features/live/frame-header-types'

/** Long enough to survive the 10s inference heartbeat, so the skip rate never reads 100%. */
const WINDOW_MS = 30_000
/** Republish twice a second - a readout does not need to repaint at frame rate. */
const TICK_MS = 500

export interface InferenceStats {
  /** Frames seen in the window. Zero until the first frame arrives. */
  frames: number
  /** Fraction of those frames the change gate kept YOLO off, 0..1. */
  skipRatio: number
  /** Median inference time over the frames YOLO actually ran on, in ms. */
  medianProcessMs: number | null
  /** True while the backend has never sent the skip flag (older deployment). */
  gateUnknown: boolean
}

const EMPTY: InferenceStats = {
  frames: 0,
  skipRatio: 0,
  medianProcessMs: null,
  gateUnknown: true,
}

interface Sample {
  at: number
  skipped: boolean
  processMs: number
}

function median(values: number[]): number | null {
  if (values.length === 0) return null
  const sorted = [...values].sort((a, b) => a - b)
  const middle = Math.floor(sorted.length / 2)
  if (sorted.length % 2 === 1) return sorted[middle] ?? null
  const low = sorted[middle - 1]
  const high = sorted[middle]
  return low === undefined || high === undefined ? null : (low + high) / 2
}

/**
 * Rolling view of what the detector is actually doing, derived entirely from
 * frame headers that the realtime socket already delivers - no extra endpoint,
 * no extra load on a board that is busy running YOLO26.
 *
 * The number worth showing is `skipRatio`. The change gate compares each frame
 * against the last one the detector looked at and only wakes YOLO when the
 * scene moved; on a car park, where cars are parked and therefore still, that
 * keeps inference off the large majority of frames and is the single reason
 * this pipeline fits on the board at all. A viewer sees the effect live.
 *
 * Samples are kept in a ref and published on a timer, never on arrival, so a
 * camera running at 20 fps cannot turn this readout into its own source of
 * re-renders.
 */
export function useInferenceStats(header: FrameHeader | null): InferenceStats {
  const samplesRef = useRef<Sample[]>([])
  const seenSeqRef = useRef<string | null>(null)
  const cameraRef = useRef<number | null>(null)
  const [stats, setStats] = useState<InferenceStats>(EMPTY)

  // Discarding on camera change happens HERE rather than in its own
  // `[cameraId]` effect. A separate effect runs after this one on mount and
  // would throw away the very first frame's sample every time the component
  // mounts - which for a single-frame render means no stats at all.
  useEffect(() => {
    if (header === null) return

    if (cameraRef.current !== header.camera_id) {
      // A different camera is a different scene with different motion; its
      // predecessor's frames say nothing about it.
      cameraRef.current = header.camera_id
      samplesRef.current = []
      seenSeqRef.current = null
    }

    // One sample per frame: React may re-render with the same header object,
    // and counting it twice would skew the ratio toward whatever that frame was.
    const key = `${header.camera_id}:${header.seq}`
    if (seenSeqRef.current === key) return
    seenSeqRef.current = key
    samplesRef.current.push({
      at: Date.now(),
      skipped: header.inference_skipped === true,
      processMs: header.process_ms,
    })
  }, [header])

  useEffect(() => {
    const timer = setInterval(() => {
      const cutoff = Date.now() - WINDOW_MS
      const kept = samplesRef.current.filter((sample) => sample.at >= cutoff)
      samplesRef.current = kept
      if (kept.length === 0) {
        setStats(EMPTY)
        return
      }
      const skipped = kept.filter((sample) => sample.skipped)
      const inferred = kept.filter((sample) => !sample.skipped)
      setStats({
        frames: kept.length,
        skipRatio: skipped.length / kept.length,
        medianProcessMs: median(inferred.map((sample) => sample.processMs)),
        // A backend that never sets the flag is indistinguishable from a scene
        // that never stops moving; say "unknown" rather than claim 0% saved.
        gateUnknown: skipped.length === 0 && inferred.every((sample) => sample.processMs > 0),
      })
    }, TICK_MS)
    return () => clearInterval(timer)
  }, [])

  return stats
}
