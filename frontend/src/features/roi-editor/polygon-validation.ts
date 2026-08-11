import type { Point } from './coordinate-transform'
import type { EditorSlot } from './roi-editor-types'

/**
 * Mirrors `backend/caps_dash/api/schemas/polygon_schemas.py` (MIN_POINTS,
 * MAX_POINTS, MIN_AREA_PX) so the client rejects an obviously-bad polygon
 * before spending a round trip on it. The backend remains the authority -
 * this is a client-side convenience, not a substitute (see phase-11 plan
 * "Security Considerations").
 */
export const MIN_POLYGON_POINTS = 3
export const MAX_POLYGON_POINTS = 64
export const MIN_POLYGON_AREA_PX = 100

export type SlotValidationErrorReason =
  | 'TOO_FEW_VERTICES'
  | 'TOO_MANY_VERTICES'
  | 'DEGENERATE_AREA'
  | 'EMPTY_CODE'
  | 'DUPLICATE_CODE'

export interface SlotValidationError {
  slotKey: string
  code: string
  reason: SlotValidationErrorReason
}

export interface SlotValidationWarning {
  slotKey: string
  code: string
  reason: 'SELF_INTERSECTING'
}

export interface ValidationResult {
  errors: SlotValidationError[]
  warnings: SlotValidationWarning[]
}

/** Shoelace formula - identical to the backend's `_shoelace_area`. */
export function polygonArea(points: Point[]): number {
  let total = 0
  const count = points.length
  for (let index = 0; index < count; index += 1) {
    const current = points[index]
    const next = points[(index + 1) % count]
    if (!current || !next) continue
    total += current.x * next.y - next.x * current.y
  }
  return Math.abs(total) / 2
}

/**
 * Cheap O(n^2) segment-intersection check. Twelve polygons of ~8 vertices
 * each keeps this trivially fast; it exists to WARN, not block - ray casting
 * against a self-intersecting shape still works, and operators sometimes
 * draw odd concave shapes on purpose around a pillar or ramp.
 */
export function isSelfIntersecting(points: Point[]): boolean {
  const count = points.length
  if (count < 4) return false
  for (let i = 0; i < count; i += 1) {
    const a1 = points[i]
    const a2 = points[(i + 1) % count]
    if (!a1 || !a2) continue
    for (let j = i + 1; j < count; j += 1) {
      // Adjacent edges always share an endpoint - that is not an intersection.
      if (j === i || j === (i + 1) % count || (j + 1) % count === i) continue
      const b1 = points[j]
      const b2 = points[(j + 1) % count]
      if (!b1 || !b2) continue
      if (segmentsIntersect(a1, a2, b1, b2)) return true
    }
  }
  return false
}

function segmentsIntersect(p1: Point, p2: Point, p3: Point, p4: Point): boolean {
  const d1 = cross(p3, p4, p1)
  const d2 = cross(p3, p4, p2)
  const d3 = cross(p1, p2, p3)
  const d4 = cross(p1, p2, p4)
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))
}

function cross(origin: Point, a: Point, b: Point): number {
  return (a.x - origin.x) * (b.y - origin.y) - (a.y - origin.y) * (b.x - origin.x)
}

/** Every check a Save must pass, plus non-blocking warnings, across the whole slot list. */
export function validateAll(slots: EditorSlot[]): ValidationResult {
  const errors: SlotValidationError[] = []
  const warnings: SlotValidationWarning[] = []
  const seenCodes = new Map<string, number>()

  for (const slot of slots) {
    seenCodes.set(slot.code, (seenCodes.get(slot.code) ?? 0) + 1)

    if (slot.code.trim().length === 0) {
      errors.push({ slotKey: slot.key, code: slot.code, reason: 'EMPTY_CODE' })
    }
    if (slot.points.length < MIN_POLYGON_POINTS) {
      errors.push({ slotKey: slot.key, code: slot.code, reason: 'TOO_FEW_VERTICES' })
    } else if (slot.points.length > MAX_POLYGON_POINTS) {
      errors.push({ slotKey: slot.key, code: slot.code, reason: 'TOO_MANY_VERTICES' })
    } else if (polygonArea(slot.points) < MIN_POLYGON_AREA_PX) {
      errors.push({ slotKey: slot.key, code: slot.code, reason: 'DEGENERATE_AREA' })
    } else if (isSelfIntersecting(slot.points)) {
      warnings.push({ slotKey: slot.key, code: slot.code, reason: 'SELF_INTERSECTING' })
    }
  }

  for (const [code, count] of seenCodes) {
    if (count <= 1) continue
    for (const slot of slots.filter((s) => s.code === code)) {
      errors.push({ slotKey: slot.key, code, reason: 'DUPLICATE_CODE' })
    }
  }

  return { errors, warnings }
}
