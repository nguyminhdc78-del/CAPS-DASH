import type { FrameSize, Point } from './coordinate-transform'
import {
  cloneSlots,
  generateDefaultCode,
  generateSlotKey,
  MIN_SLOT_VERTICES,
  pushHistory,
  slotsEqual,
} from './roi-editor-reducer-helpers'
import type { EditorSelection, EditorSlot, RoiEditorState } from './roi-editor-types'

/**
 * Pure reducer - no Konva imports, fully unit-testable (see
 * tests/features/roi-editor/use-roi-editor-state.test.ts).
 *
 * History discipline: most mutations push one history entry per dispatch.
 * Dragging is the deliberate exception - `BEGIN_DRAG` snapshots once at drag
 * start, then `MOVE_VERTEX`/`MOVE_POLYGON` apply on every pointer-move
 * WITHOUT pushing further history, because the operator's actual undo unit
 * for a drag is "the whole drag", not "one animation frame of it".
 */
export type RoiEditorAction =
  | { type: 'LOAD'; slots: EditorSlot[]; sourceFrame: FrameSize }
  | { type: 'ADD_VERTEX'; point: Point }
  | { type: 'CLOSE_DRAFT' }
  | { type: 'CANCEL_DRAFT' }
  | { type: 'BEGIN_DRAG' }
  | { type: 'MOVE_VERTEX'; slotKey: string; vertexIndex: number; point: Point }
  | { type: 'MOVE_POLYGON'; slotKey: string; dx: number; dy: number }
  | { type: 'INSERT_VERTEX'; slotKey: string; afterIndex: number; point: Point }
  | { type: 'DELETE_VERTEX'; slotKey: string; vertexIndex: number }
  | { type: 'DELETE_SLOT'; slotKey: string }
  | { type: 'RENAME_SLOT'; slotKey: string; code?: string; floor?: string }
  | { type: 'SELECT'; selection: EditorSelection | null }
  | { type: 'UNDO' }
  | { type: 'REDO' }
  | { type: 'MARK_SAVED' }

export const initialRoiEditorState: RoiEditorState = {
  slots: [],
  draft: null,
  selection: null,
  history: { past: [], future: [] },
  baseline: [],
  dirty: false,
  sourceFrame: null,
}

export function roiEditorReducer(state: RoiEditorState, action: RoiEditorAction): RoiEditorState {
  switch (action.type) {
    case 'LOAD':
      return {
        slots: action.slots,
        draft: null,
        selection: null,
        history: { past: [], future: [] },
        baseline: cloneSlots(action.slots),
        dirty: false,
        sourceFrame: action.sourceFrame,
      }

    case 'ADD_VERTEX':
      return { ...state, draft: [...(state.draft ?? []), action.point] }

    case 'CLOSE_DRAFT': {
      if (!state.draft || state.draft.length < MIN_SLOT_VERTICES) return state
      const newSlot: EditorSlot = {
        key: generateSlotKey(),
        code: generateDefaultCode(state.slots.map((slot) => slot.code)),
        floor: '',
        points: state.draft,
      }
      const slots = [...state.slots, newSlot]
      return {
        ...state,
        slots,
        draft: null,
        selection: { slotKey: newSlot.key, vertexIndex: null },
        history: pushHistory(state.history, state.slots),
        dirty: !slotsEqual(slots, state.baseline),
      }
    }

    case 'CANCEL_DRAFT':
      return { ...state, draft: null }

    case 'BEGIN_DRAG':
      return { ...state, history: pushHistory(state.history, state.slots) }

    case 'MOVE_VERTEX': {
      const slots = mapSlot(state.slots, action.slotKey, (slot) => ({
        ...slot,
        points: slot.points.map((point, index) => (index === action.vertexIndex ? action.point : point)),
      }))
      return { ...state, slots, dirty: !slotsEqual(slots, state.baseline) }
    }

    case 'MOVE_POLYGON': {
      const slots = mapSlot(state.slots, action.slotKey, (slot) => ({
        ...slot,
        points: slot.points.map((point) => ({ x: point.x + action.dx, y: point.y + action.dy })),
      }))
      return { ...state, slots, dirty: !slotsEqual(slots, state.baseline) }
    }

    case 'INSERT_VERTEX': {
      const history = pushHistory(state.history, state.slots)
      const slots = mapSlot(state.slots, action.slotKey, (slot) => ({
        ...slot,
        points: [
          ...slot.points.slice(0, action.afterIndex + 1),
          action.point,
          ...slot.points.slice(action.afterIndex + 1),
        ],
      }))
      return { ...state, slots, history, dirty: !slotsEqual(slots, state.baseline) }
    }

    case 'DELETE_VERTEX': {
      const target = state.slots.find((slot) => slot.key === action.slotKey)
      // Blocked below MIN_SLOT_VERTICES: a 2-vertex "polygon" cannot be
      // saved anyway (polygon-validation.ts / backend both reject it), so
      // removing a third vertex would only strand the operator with a shape
      // Save can never accept.
      if (!target || target.points.length <= MIN_SLOT_VERTICES) return state
      const history = pushHistory(state.history, state.slots)
      const slots = mapSlot(state.slots, action.slotKey, (slot) => ({
        ...slot,
        points: slot.points.filter((_, index) => index !== action.vertexIndex),
      }))
      return { ...state, slots, history, selection: null, dirty: !slotsEqual(slots, state.baseline) }
    }

    case 'DELETE_SLOT': {
      const history = pushHistory(state.history, state.slots)
      const slots = state.slots.filter((slot) => slot.key !== action.slotKey)
      return { ...state, slots, history, selection: null, dirty: !slotsEqual(slots, state.baseline) }
    }

    case 'RENAME_SLOT': {
      const history = pushHistory(state.history, state.slots)
      const slots = mapSlot(state.slots, action.slotKey, (slot) => ({
        ...slot,
        ...(action.code !== undefined ? { code: action.code } : {}),
        ...(action.floor !== undefined ? { floor: action.floor } : {}),
      }))
      return { ...state, slots, history, dirty: !slotsEqual(slots, state.baseline) }
    }

    case 'SELECT':
      return { ...state, selection: action.selection }

    case 'UNDO': {
      const previous = state.history.past[state.history.past.length - 1]
      if (previous === undefined) return state
      return {
        ...state,
        slots: previous,
        selection: null,
        draft: null,
        history: {
          past: state.history.past.slice(0, -1),
          future: [cloneSlots(state.slots), ...state.history.future],
        },
        dirty: !slotsEqual(previous, state.baseline),
      }
    }

    case 'REDO': {
      const next = state.history.future[0]
      if (next === undefined) return state
      return {
        ...state,
        slots: next,
        selection: null,
        draft: null,
        history: {
          past: [...state.history.past, cloneSlots(state.slots)],
          future: state.history.future.slice(1),
        },
        dirty: !slotsEqual(next, state.baseline),
      }
    }

    case 'MARK_SAVED':
      return { ...state, baseline: cloneSlots(state.slots), dirty: false }

    default:
      return state
  }
}

function mapSlot(
  slots: EditorSlot[],
  slotKey: string,
  update: (slot: EditorSlot) => EditorSlot,
): EditorSlot[] {
  return slots.map((slot) => (slot.key === slotKey ? update(slot) : slot))
}
