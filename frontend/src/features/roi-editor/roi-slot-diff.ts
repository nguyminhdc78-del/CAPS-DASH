import type { Point } from './coordinate-transform'
import type { EditorSlot } from './roi-editor-types'

/** Added/modified/removed codes between the loaded baseline and the current
 * edit, for the save-confirm dialog - and `removed` doubles as exactly the
 * list the backend needs `allow_delete=true` to confirm losing (deleting a
 * slot cascades its `slot_state_history`; see slot_map_service.py). */
export interface SlotMapDiff {
  added: string[]
  modified: string[]
  removed: string[]
}

export function diffSlots(baseline: EditorSlot[], current: EditorSlot[]): SlotMapDiff {
  const baselineByCode = new Map(baseline.map((slot) => [slot.code, slot]))
  const currentCodes = new Set(current.map((slot) => slot.code))

  const added: string[] = []
  const modified: string[] = []
  for (const slot of current) {
    const before = baselineByCode.get(slot.code)
    if (!before) {
      added.push(slot.code)
      continue
    }
    if (before.floor !== slot.floor || !pointsEqual(before.points, slot.points)) {
      modified.push(slot.code)
    }
  }

  const removed = baseline.filter((slot) => !currentCodes.has(slot.code)).map((slot) => slot.code)

  return { added: added.sort(), modified: modified.sort(), removed: removed.sort() }
}

function pointsEqual(a: Point[], b: Point[]): boolean {
  if (a.length !== b.length) return false
  return a.every((point, index) => {
    const other = b[index]
    return other !== undefined && point.x === other.x && point.y === other.y
  })
}
