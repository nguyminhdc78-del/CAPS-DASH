import type { FrameSize } from './coordinate-transform'
import type { EditorSlot } from './roi-editor-types'

/**
 * Editor state -> the exact `PUT /cameras/{id}/slot-map` body, matching
 * `SlotMapRequest` in backend/caps_dash/api/schemas/camera_schemas.py.
 *
 * `src_frame_width`/`src_frame_height` come from the CURRENT snapshot's
 * natural dimensions (`image.naturalWidth/Height`, passed in as
 * `snapshotFrame`) - never from the display box. The display box is a CSS/
 * canvas layout size that shrinks and grows with the browser window; sending
 * it as if it were the frame size would silently persist display pixels,
 * which is precisely the bug coordinate-transform.ts exists to prevent.
 */

export interface SlotMapPolygonPayload {
  points: [number, number][]
}

export interface SlotMapSlotPayload {
  code: string
  floor: string
  polygon: SlotMapPolygonPayload
}

export interface SlotMapPayload {
  src_frame_width: number
  src_frame_height: number
  slots: SlotMapSlotPayload[]
  allow_delete: boolean
}

export function buildSlotMapPayload(
  slots: EditorSlot[],
  snapshotFrame: FrameSize,
  allowDelete: boolean,
): SlotMapPayload {
  return {
    src_frame_width: Math.round(snapshotFrame.width),
    src_frame_height: Math.round(snapshotFrame.height),
    slots: slots.map((slot) => ({
      code: slot.code,
      floor: slot.floor,
      polygon: { points: slot.points.map((point) => [point.x, point.y]) },
    })),
    allow_delete: allowDelete,
  }
}
