import { useReducer } from 'react'

import type { FrameSize, Point } from './coordinate-transform'
import { initialRoiEditorState, roiEditorReducer } from './roi-editor-reducer'
import type { EditorSelection, EditorSlot } from './roi-editor-types'

/**
 * Ergonomic wrapper around the pure reducer: one named function per gesture
 * instead of components building action objects inline. The reducer itself
 * (roi-editor-reducer.ts) stays framework-free and is what the unit tests
 * exercise directly.
 */
export function useRoiEditorState() {
  const [state, dispatch] = useReducer(roiEditorReducer, initialRoiEditorState)

  const drafting = (state.draft?.length ?? 0) > 0

  return {
    state,
    drafting,
    // While a polygon is being drawn, "undo" means "take back that last
    // point" - which is what an operator mid-draw actually wants, and what
    // the history stack cannot express because a draft is not a slot yet.
    canUndo: drafting || state.history.past.length > 0,
    canRedo: state.history.future.length > 0,

    loadSlots: (slots: EditorSlot[], sourceFrame: FrameSize) =>
      dispatch({ type: 'LOAD', slots, sourceFrame }),
    addVertex: (point: Point) => dispatch({ type: 'ADD_VERTEX', point }),
    removeLastVertex: () => dispatch({ type: 'REMOVE_LAST_VERTEX' }),
    closeDraft: () => dispatch({ type: 'CLOSE_DRAFT' }),
    cancelDraft: () => dispatch({ type: 'CANCEL_DRAFT' }),
    beginDrag: () => dispatch({ type: 'BEGIN_DRAG' }),
    moveVertex: (slotKey: string, vertexIndex: number, point: Point) =>
      dispatch({ type: 'MOVE_VERTEX', slotKey, vertexIndex, point }),
    movePolygon: (slotKey: string, dx: number, dy: number) =>
      dispatch({ type: 'MOVE_POLYGON', slotKey, dx, dy }),
    insertVertex: (slotKey: string, afterIndex: number, point: Point) =>
      dispatch({ type: 'INSERT_VERTEX', slotKey, afterIndex, point }),
    deleteVertex: (slotKey: string, vertexIndex: number) =>
      dispatch({ type: 'DELETE_VERTEX', slotKey, vertexIndex }),
    deleteSlot: (slotKey: string) => dispatch({ type: 'DELETE_SLOT', slotKey }),
    renameSlot: (slotKey: string, patch: { code?: string; floor?: string }) =>
      dispatch({ type: 'RENAME_SLOT', slotKey, ...patch }),
    select: (selection: EditorSelection | null) => dispatch({ type: 'SELECT', selection }),
    undo: () => dispatch({ type: 'UNDO' }),
    redo: () => dispatch({ type: 'REDO' }),
    markSaved: () => dispatch({ type: 'MARK_SAVED' }),
  }
}

export type RoiEditorApi = ReturnType<typeof useRoiEditorState>
