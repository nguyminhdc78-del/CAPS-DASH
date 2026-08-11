import { MIN_POLYGON_POINTS } from './polygon-validation'
import type { EditorSlot, HistoryState } from './roi-editor-types'

/** >= 30 per phase-11 plan; 50 gives headroom above the minimum without the
 * per-step clone arrays (12 polygons x ~8 points, tiny) ever adding up to a
 * meaningful amount of memory. */
export const HISTORY_LIMIT = 50

export const MIN_SLOT_VERTICES = MIN_POLYGON_POINTS

/** Deep-clone the parts of state that get mutated in place elsewhere, so a
 * pushed history entry can never be retroactively changed by a later edit. */
export function cloneSlots(slots: EditorSlot[]): EditorSlot[] {
  return slots.map((slot) => ({ ...slot, points: slot.points.map((point) => ({ ...point })) }))
}

/** Push the CURRENT (pre-mutation) slots onto `past`, capped, and clear
 * `future` - a fresh edit after an undo invalidates the redone-from branch,
 * same as every other undo stack. */
export function pushHistory(history: HistoryState, currentSlots: EditorSlot[]): HistoryState {
  const past = [...history.past, cloneSlots(currentSlots)].slice(-HISTORY_LIMIT)
  return { past, future: [] }
}

/** Order-sensitive content equality, used only to decide the `dirty` flag
 * against `baseline` - not a general-purpose deep-equal. */
export function slotsEqual(a: EditorSlot[], b: EditorSlot[]): boolean {
  if (a.length !== b.length) return false
  return a.every((slotA, index) => {
    const slotB = b[index]
    if (!slotB) return false
    if (slotA.key !== slotB.key || slotA.code !== slotB.code || slotA.floor !== slotB.floor) return false
    if (slotA.points.length !== slotB.points.length) return false
    return slotA.points.every((point, pointIndex) => {
      const other = slotB.points[pointIndex]
      return other !== undefined && point.x === other.x && point.y === other.y
    })
  })
}

/** First unused "NEW-n" code, so a freshly-closed polygon is never saved
 * with an empty code by accident - the operator can still rename it inline. */
export function generateDefaultCode(existingCodes: string[]): string {
  const taken = new Set(existingCodes)
  let n = 1
  while (taken.has(`NEW-${n}`)) n += 1
  return `NEW-${n}`
}

let keyCounter = 0

/**
 * A React key for a slot being edited. Never persisted, never sent anywhere.
 *
 * NOT `crypto.randomUUID()`: that function only exists in a **secure
 * context**, so it is there on `localhost` during development and gone the
 * moment the dashboard is served from the board's LAN address over plain
 * HTTP - which is exactly how this product is deployed. It crashed the whole
 * ROI editor with "crypto.randomUUID is not a function" while every
 * development machine looked fine.
 *
 * A counter plus a timestamp is enough: these keys only have to be unique
 * within one editing session in one tab.
 */
export function generateSlotKey(): string {
  keyCounter += 1
  return `slot-${Date.now().toString(36)}-${keyCounter}`
}
