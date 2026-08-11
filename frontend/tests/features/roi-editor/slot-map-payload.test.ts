import { describe, expect, it } from 'vitest'

import { buildSlotMapPayload } from '@/features/roi-editor/slot-map-payload'
import type { EditorSlot } from '@/features/roi-editor/roi-editor-types'

const SLOTS: EditorSlot[] = [
  {
    key: 'k1',
    code: 'A1',
    floor: 'B1',
    points: [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
      { x: 100, y: 100 },
      { x: 0, y: 100 },
    ],
  },
]

describe('buildSlotMapPayload', () => {
  it('uses the snapshot natural size, not any display-box size', () => {
    // A display box (e.g. a browser fit to a small window) that is
    // DELIBERATELY different from the snapshot's natural size, to prove the
    // payload never picks it up.
    const snapshotFrame = { width: 1600, height: 900 }
    const payload = buildSlotMapPayload(SLOTS, snapshotFrame, false)
    expect(payload.src_frame_width).toBe(1600)
    expect(payload.src_frame_height).toBe(900)
  })

  it('maps slots to the exact backend shape: code, floor, polygon.points as [x, y] tuples', () => {
    const payload = buildSlotMapPayload(SLOTS, { width: 1600, height: 900 }, false)
    expect(payload.slots).toEqual([
      {
        code: 'A1',
        floor: 'B1',
        polygon: {
          points: [
            [0, 0],
            [100, 0],
            [100, 100],
            [0, 100],
          ],
        },
      },
    ])
  })

  it('carries allow_delete through untouched', () => {
    expect(buildSlotMapPayload(SLOTS, { width: 1600, height: 900 }, true).allow_delete).toBe(true)
    expect(buildSlotMapPayload(SLOTS, { width: 1600, height: 900 }, false).allow_delete).toBe(false)
  })

  it('rounds fractional natural dimensions to whole pixels', () => {
    const payload = buildSlotMapPayload(SLOTS, { width: 1599.6, height: 900.4 }, false)
    expect(payload.src_frame_width).toBe(1600)
    expect(payload.src_frame_height).toBe(900)
  })

  it('produces an empty slots array for an empty editor', () => {
    const payload = buildSlotMapPayload([], { width: 1600, height: 900 }, false)
    expect(payload.slots).toEqual([])
  })
})
