import { useEffect, useRef, useState } from 'react'

import type { FrameSize } from './coordinate-transform'
import { rescaleToFrame } from './coordinate-transform'
import { generateSlotKey } from './roi-editor-reducer-helpers'
import { useCameraSnapshot } from './use-camera-snapshot'
import { useSlotMapQuery } from './use-roi-editor-queries'
import type { RoiEditorApi } from './use-roi-editor-state'
import type { EditorSlot } from './roi-editor-types'

/**
 * Combines the snapshot and the stored slot map into one LOAD dispatch.
 *
 * The stored map's `src_frame_width/height` is normally authoritative (it is
 * what every persisted point is drawn against), EXCEPT: a brand-new camera
 * with no slots yet returns 0x0 (see `slot_map_service._to_response`), and a
 * camera whose resolution changed since the map was drawn returns a size
 * that no longer matches the snapshot just fetched. Both cases are handled
 * here, once, so every other module can treat `sourceFrame` as simply "the
 * frame everything in the reducer is expressed against" without re-deriving
 * this logic.
 */
export function useRoiEditorData(cameraId: number, editor: RoiEditorApi) {
  const snapshot = useCameraSnapshot(cameraId)
  const slotMapQuery = useSlotMapQuery(cameraId)
  const loadedForCamera = useRef<number | null>(null)
  const [frameMismatch, setFrameMismatch] = useState(false)

  useEffect(() => {
    if (loadedForCamera.current === cameraId) return
    if (snapshot.status !== 'ready' || !snapshot.image) return
    if (!slotMapQuery.data) return

    const snapshotFrame: FrameSize = {
      width: snapshot.image.naturalWidth,
      height: snapshot.image.naturalHeight,
    }
    const stored = slotMapQuery.data
    const hasStoredFrame = stored.src_frame_width > 0 && stored.src_frame_height > 0
    const storedFrame: FrameSize = hasStoredFrame
      ? { width: stored.src_frame_width, height: stored.src_frame_height }
      : snapshotFrame
    const changed =
      hasStoredFrame &&
      (storedFrame.width !== snapshotFrame.width || storedFrame.height !== snapshotFrame.height)

    const slots: EditorSlot[] = stored.slots.map((entry, index) => ({
      // Not `crypto.randomUUID()` - it does not exist outside a secure
      // context, and the dashboard is served over plain HTTP from the board.
      key: `${entry.code}-${index}-${generateSlotKey()}`,
      code: entry.code,
      floor: entry.floor,
      points: entry.polygon.points.map(([x, y]) => {
        const point = { x, y }
        return changed ? rescaleToFrame(point, storedFrame, snapshotFrame) : point
      }),
    }))

    editor.loadSlots(slots, snapshotFrame)
    setFrameMismatch(changed)
    loadedForCamera.current = cameraId
    // `editor` (the hook's return object) is recreated every render, so
    // listing it here re-runs this effect on every render - harmless,
    // because `loadedForCamera` (not a stable function reference) is what
    // actually makes the effect idempotent; the guard above turns every
    // extra invocation into a no-op.
  }, [cameraId, snapshot.status, snapshot.image, slotMapQuery.data, editor])

  return { snapshot, slotMapQuery, frameMismatch }
}
