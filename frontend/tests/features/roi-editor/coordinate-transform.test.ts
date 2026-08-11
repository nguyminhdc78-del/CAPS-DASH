import { describe, expect, it } from 'vitest'

import {
  clampToFrame,
  displayToSource,
  rescaleToFrame,
  sourceToDisplay,
} from '@/features/roi-editor/coordinate-transform'
import type { FrameSize, Point } from '@/features/roi-editor/coordinate-transform'

describe('coordinate-transform', () => {
  // The mandatory case: a non-square source and a non-square display that do
  // NOT share an aspect ratio delta trivially cancelled by a single scale.
  // 1600x900 is 16:9; 640x448 is 10:7. Getting this right requires the two
  // independent factors - a shared Math.min(scaleX, scaleY) would produce a
  // visibly different (wrong) result for at least one axis.
  const source: FrameSize = { width: 1600, height: 900 }
  const display: FrameSize = { width: 640, height: 448 }

  it('round-trips display -> source -> display at a non-square scale', () => {
    const original: Point = { x: 213.5, y: 77.25 }
    const roundTripped = displayToSource(sourceToDisplay(original, source, display), source, display)
    expect(roundTripped.x).toBeCloseTo(original.x, 6)
    expect(roundTripped.y).toBeCloseTo(original.y, 6)
  })

  it('round-trips source -> display -> source for several points, including edges', () => {
    const points: Point[] = [
      { x: 0, y: 0 },
      { x: source.width, y: source.height },
      { x: 1, y: source.height - 1 },
      { x: source.width / 3, y: source.height / 7 },
    ]
    for (const point of points) {
      const back = displayToSource(sourceToDisplay(point, source, display), source, display)
      expect(back.x).toBeCloseTo(point.x, 6)
      expect(back.y).toBeCloseTo(point.y, 6)
    }
  })

  it('applies independent x/y factors, not a shared min(scaleX, scaleY)', () => {
    // scaleX = 640/1600 = 0.4, scaleY = 448/900 = 0.4977... - deliberately
    // different, so a shared-scale implementation would fail this exact case.
    const point: Point = { x: 800, y: 450 }
    const converted = sourceToDisplay(point, source, display)
    expect(converted.x).toBeCloseTo(320, 6) // 800 * 0.4
    expect(converted.y).toBeCloseTo(224, 6) // 450 * (448/900), not 450 * 0.4 (= 180)
    expect(converted.y).not.toBeCloseTo(180, 0)
  })

  it('reprojects a point drawn against an old frame size onto a new one', () => {
    const oldFrame: FrameSize = { width: 800, height: 450 }
    const newFrame: FrameSize = { width: 1600, height: 900 }
    const point: Point = { x: 400, y: 225 } // dead centre of the old frame
    const reprojected = rescaleToFrame(point, oldFrame, newFrame)
    expect(reprojected).toEqual({ x: 800, y: 450 }) // still dead centre
  })

  it('clamps a dragged point to stay inside the frame on both axes', () => {
    const frame: FrameSize = { width: 100, height: 50 }
    expect(clampToFrame({ x: -10, y: -5 }, frame)).toEqual({ x: 0, y: 0 })
    expect(clampToFrame({ x: 500, y: 500 }, frame)).toEqual({ x: 100, y: 50 })
    expect(clampToFrame({ x: 40, y: 20 }, frame)).toEqual({ x: 40, y: 20 })
  })
})
