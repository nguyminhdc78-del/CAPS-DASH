import { describe, expect, it } from 'vitest'

import { computeContainedRect, scaleFactorsFor } from '@/features/live/overlay-geometry'

describe('computeContainedRect', () => {
  it('letterboxes top and bottom when the box is wider than the image', () => {
    const rect = computeContainedRect(1000, 500, 640, 480)
    expect(rect).not.toBeNull()
    // 640x480 into a 1000x500 box, height-constrained: height=500, width=500*(640/480)
    expect(rect!.height).toBe(500)
    expect(rect!.width).toBeCloseTo(666.67, 1)
    expect(rect!.top).toBe(0)
    expect(rect!.left).toBeCloseTo((1000 - rect!.width) / 2, 5)
  })

  it('returns null for a zero-size box or image', () => {
    expect(computeContainedRect(0, 500, 640, 480)).toBeNull()
    expect(computeContainedRect(1000, 500, 0, 480)).toBeNull()
  })
})

describe('scaleFactorsFor', () => {
  it('computes independent x and y factors, never a single shared scale', () => {
    // A rendered rect whose aspect ratio does NOT match frame_w/frame_h -
    // the case the hard rule exists for.
    const rect = { left: 0, top: 0, width: 800, height: 300 }
    const { x, y } = scaleFactorsFor(rect, 640, 480)

    expect(x).toBeCloseTo(800 / 640, 10)
    expect(y).toBeCloseTo(300 / 480, 10)
    expect(x).not.toBeCloseTo(y, 2) // the two factors must be free to differ
  })
})
