import { describe, expect, it } from 'vitest'

import { isSelfIntersecting, polygonArea, validateAll } from '@/features/roi-editor/polygon-validation'
import type { EditorSlot } from '@/features/roi-editor/roi-editor-types'

function square(size: number): EditorSlot['points'] {
  return [
    { x: 0, y: 0 },
    { x: size, y: 0 },
    { x: size, y: size },
    { x: 0, y: size },
  ]
}

function slot(overrides: Partial<EditorSlot>): EditorSlot {
  return { key: 'k1', code: 'A1', floor: 'B1', points: square(50), ...overrides }
}

describe('polygon-validation', () => {
  it('computes the shoelace area of a simple square', () => {
    expect(polygonArea(square(10))).toBeCloseTo(100, 6)
  })

  it('rejects a polygon with fewer than 3 vertices', () => {
    const result = validateAll([slot({ points: [{ x: 0, y: 0 }, { x: 1, y: 1 }] })])
    expect(result.errors).toContainEqual({ slotKey: 'k1', code: 'A1', reason: 'TOO_FEW_VERTICES' })
  })

  it('rejects a degenerate (collinear, near-zero-area) polygon', () => {
    const collinear = [
      { x: 0, y: 0 },
      { x: 5, y: 0 },
      { x: 10, y: 0 },
    ]
    const result = validateAll([slot({ points: collinear })])
    expect(result.errors).toContainEqual({ slotKey: 'k1', code: 'A1', reason: 'DEGENERATE_AREA' })
  })

  it('rejects an area below the 100px^2 floor even when not collinear', () => {
    const result = validateAll([slot({ points: square(5) })]) // area = 25
    expect(result.errors).toContainEqual({ slotKey: 'k1', code: 'A1', reason: 'DEGENERATE_AREA' })
  })

  it('accepts a valid square well above the area floor', () => {
    const result = validateAll([slot({ points: square(50) })])
    expect(result.errors).toEqual([])
  })

  it('rejects an empty code', () => {
    const result = validateAll([slot({ code: '' })])
    expect(result.errors).toContainEqual({ slotKey: 'k1', code: '', reason: 'EMPTY_CODE' })
  })

  it('rejects duplicate codes across slots', () => {
    const result = validateAll([
      slot({ key: 'k1', code: 'A1' }),
      slot({ key: 'k2', code: 'A1' }),
    ])
    expect(result.errors).toContainEqual({ slotKey: 'k1', code: 'A1', reason: 'DUPLICATE_CODE' })
    expect(result.errors).toContainEqual({ slotKey: 'k2', code: 'A1', reason: 'DUPLICATE_CODE' })
  })

  it('detects a self-intersecting (bowtie) polygon as a warning, not an error', () => {
    // Deliberately asymmetric so the shoelace formula's signed lobes do not
    // cancel to ~0 (a symmetric bowtie would, incorrectly tripping
    // DEGENERATE_AREA instead of exercising the warning path this test wants).
    const bowtie = [
      { x: 0, y: 0 },
      { x: 100, y: 60 },
      { x: 100, y: 0 },
      { x: 0, y: 100 },
    ]
    expect(isSelfIntersecting(bowtie)).toBe(true)
    const result = validateAll([slot({ points: bowtie })])
    expect(result.errors).toEqual([])
    expect(result.warnings).toContainEqual({ slotKey: 'k1', code: 'A1', reason: 'SELF_INTERSECTING' })
  })

  it('does not flag a simple convex polygon as self-intersecting', () => {
    expect(isSelfIntersecting(square(50))).toBe(false)
  })
})
