import { describe, expect, it } from 'vitest'

import type { FrameSize } from '@/features/roi-editor/coordinate-transform'
import { HISTORY_LIMIT } from '@/features/roi-editor/roi-editor-reducer-helpers'
import { initialRoiEditorState, roiEditorReducer } from '@/features/roi-editor/roi-editor-reducer'
import type { RoiEditorAction } from '@/features/roi-editor/roi-editor-reducer'
import type { EditorSlot, RoiEditorState } from '@/features/roi-editor/roi-editor-types'

const FRAME: FrameSize = { width: 1600, height: 900 }

function square(key: string, code: string, size = 50): EditorSlot {
  return {
    key,
    code,
    floor: 'B1',
    points: [
      { x: 0, y: 0 },
      { x: size, y: 0 },
      { x: size, y: size },
      { x: 0, y: size },
    ],
  }
}

function reduceAll(actions: RoiEditorAction[], initial: RoiEditorState = initialRoiEditorState): RoiEditorState {
  return actions.reduce(roiEditorReducer, initial)
}

describe('roiEditorReducer', () => {
  it('LOAD sets slots, baseline and sourceFrame, and clears dirty/history', () => {
    const slots = [square('a', 'A1')]
    const state = roiEditorReducer(initialRoiEditorState, { type: 'LOAD', slots, sourceFrame: FRAME })
    expect(state.slots).toEqual(slots)
    expect(state.baseline).toEqual(slots)
    expect(state.sourceFrame).toEqual(FRAME)
    expect(state.dirty).toBe(false)
    expect(state.history).toEqual({ past: [], future: [] })
  })

  it('drawing a triangle then closing it commits a new slot and marks dirty', () => {
    const state = reduceAll([
      { type: 'LOAD', slots: [], sourceFrame: FRAME },
      { type: 'ADD_VERTEX', point: { x: 0, y: 0 } },
      { type: 'ADD_VERTEX', point: { x: 10, y: 0 } },
      { type: 'ADD_VERTEX', point: { x: 10, y: 10 } },
      { type: 'CLOSE_DRAFT' },
    ])
    expect(state.slots).toHaveLength(1)
    expect(state.slots[0]?.points).toHaveLength(3)
    expect(state.draft).toBeNull()
    expect(state.dirty).toBe(true)
  })

  it('CLOSE_DRAFT with fewer than 3 vertices is a no-op', () => {
    const state = reduceAll([
      { type: 'LOAD', slots: [], sourceFrame: FRAME },
      { type: 'ADD_VERTEX', point: { x: 0, y: 0 } },
      { type: 'ADD_VERTEX', point: { x: 10, y: 0 } },
      { type: 'CLOSE_DRAFT' },
    ])
    expect(state.slots).toHaveLength(0)
    expect(state.draft).toHaveLength(2)
  })

  it('CANCEL_DRAFT clears the in-progress polygon without touching history', () => {
    const state = reduceAll([
      { type: 'LOAD', slots: [], sourceFrame: FRAME },
      { type: 'ADD_VERTEX', point: { x: 0, y: 0 } },
      { type: 'CANCEL_DRAFT' },
    ])
    expect(state.draft).toBeNull()
    expect(state.history.past).toHaveLength(0)
  })

  describe('undo/redo', () => {
    it('undo restores a deleted vertex; redo removes it again', () => {
      const loaded = reduceAll([{ type: 'LOAD', slots: [square('a', 'A1')], sourceFrame: FRAME }])
      const afterDelete = roiEditorReducer(loaded, {
        type: 'DELETE_VERTEX',
        slotKey: 'a',
        vertexIndex: 0,
      })
      expect(afterDelete.slots[0]?.points).toHaveLength(3)

      const afterUndo = roiEditorReducer(afterDelete, { type: 'UNDO' })
      expect(afterUndo.slots[0]?.points).toHaveLength(4)
      expect(afterUndo.slots[0]?.points).toEqual(loaded.slots[0]?.points)

      const afterRedo = roiEditorReducer(afterUndo, { type: 'REDO' })
      expect(afterRedo.slots[0]?.points).toHaveLength(3)
    })

    it('UNDO on an empty history stack is a no-op', () => {
      const loaded = reduceAll([{ type: 'LOAD', slots: [square('a', 'A1')], sourceFrame: FRAME }])
      const state = roiEditorReducer(loaded, { type: 'UNDO' })
      expect(state).toBe(loaded)
    })

    it('a new mutating action after an undo clears the redo branch', () => {
      const loaded = reduceAll([{ type: 'LOAD', slots: [square('a', 'A1')], sourceFrame: FRAME }])
      const afterDelete = roiEditorReducer(loaded, { type: 'DELETE_VERTEX', slotKey: 'a', vertexIndex: 0 })
      const afterUndo = roiEditorReducer(afterDelete, { type: 'UNDO' })
      const afterRename = roiEditorReducer(afterUndo, { type: 'RENAME_SLOT', slotKey: 'a', code: 'B2' })
      expect(afterRename.history.future).toHaveLength(0)
    })

    it('history depth holds for at least 30 undo steps', () => {
      const initial = reduceAll([{ type: 'LOAD', slots: [square('a', 'A1', 500)], sourceFrame: FRAME }])
      const steps = 35
      let state = initial
      for (let i = 0; i < steps; i += 1) {
        state = roiEditorReducer(state, {
          type: 'INSERT_VERTEX',
          slotKey: 'a',
          afterIndex: 0,
          point: { x: i + 1, y: i + 1 },
        })
      }
      expect(state.slots[0]?.points).toHaveLength(4 + steps)

      let undone = state
      for (let i = 0; i < 30; i += 1) {
        undone = roiEditorReducer(undone, { type: 'UNDO' })
      }
      // 30 undos from a history capped at HISTORY_LIMIT must succeed and keep
      // removing vertices, proving the cap (>= 30 per the plan) really holds.
      expect(undone.slots[0]?.points.length).toBe(4 + steps - 30)
      expect(HISTORY_LIMIT).toBeGreaterThanOrEqual(30)
    })
  })

  describe('vertex deletion below three', () => {
    it('refuses to delete a vertex that would drop a polygon below 3 points', () => {
      const triangle: EditorSlot = { key: 'a', code: 'A1', floor: 'B1', points: [
        { x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 },
      ] }
      const loaded = reduceAll([{ type: 'LOAD', slots: [triangle], sourceFrame: FRAME }])
      const state = roiEditorReducer(loaded, { type: 'DELETE_VERTEX', slotKey: 'a', vertexIndex: 0 })
      expect(state.slots[0]?.points).toHaveLength(3)
      expect(state).toBe(loaded) // untouched: no history push, no dirty flip
    })

    it('allows deleting down to exactly 3 vertices from a square', () => {
      const loaded = reduceAll([{ type: 'LOAD', slots: [square('a', 'A1')], sourceFrame: FRAME }])
      const state = roiEditorReducer(loaded, { type: 'DELETE_VERTEX', slotKey: 'a', vertexIndex: 0 })
      expect(state.slots[0]?.points).toHaveLength(3)
    })
  })

  describe('dragging does not spam history', () => {
    it('BEGIN_DRAG snapshots once; repeated MOVE_VERTEX calls push nothing further', () => {
      const loaded = reduceAll([{ type: 'LOAD', slots: [square('a', 'A1')], sourceFrame: FRAME }])
      let state = roiEditorReducer(loaded, { type: 'BEGIN_DRAG' })
      expect(state.history.past).toHaveLength(1)
      for (let i = 0; i < 10; i += 1) {
        state = roiEditorReducer(state, {
          type: 'MOVE_VERTEX',
          slotKey: 'a',
          vertexIndex: 0,
          point: { x: i, y: i },
        })
      }
      expect(state.history.past).toHaveLength(1)
      expect(state.slots[0]?.points[0]).toEqual({ x: 9, y: 9 })

      const undone = roiEditorReducer(state, { type: 'UNDO' })
      expect(undone.slots[0]?.points[0]).toEqual({ x: 0, y: 0 })
    })
  })

  it('MARK_SAVED resets baseline to the current slots and clears dirty', () => {
    const loaded = reduceAll([{ type: 'LOAD', slots: [square('a', 'A1')], sourceFrame: FRAME }])
    const edited = roiEditorReducer(loaded, { type: 'DELETE_VERTEX', slotKey: 'a', vertexIndex: 0 })
    expect(edited.dirty).toBe(true)
    const saved = roiEditorReducer(edited, { type: 'MARK_SAVED' })
    expect(saved.dirty).toBe(false)
    expect(saved.baseline).toEqual(saved.slots)
  })

  it('DELETE_SLOT removes the slot and clears selection', () => {
    const loaded = reduceAll([
      { type: 'LOAD', slots: [square('a', 'A1'), square('b', 'B1')], sourceFrame: FRAME },
      { type: 'SELECT', selection: { slotKey: 'a', vertexIndex: null } },
    ])
    const state = roiEditorReducer(loaded, { type: 'DELETE_SLOT', slotKey: 'a' })
    expect(state.slots.map((s) => s.key)).toEqual(['b'])
    expect(state.selection).toBeNull()
  })
})

describe('taking back a point while drawing', () => {
  /**
   * The reported failure: "vẽ cho đã, không back lại được". `ADD_VERTEX`
   * pushes no history entry, so Ctrl+Z during a draw could never step back a
   * point - and `UNDO` clears `draft`, so pressing it mid-draw destroyed the
   * whole half-drawn polygon instead.
   */
  it('REMOVE_LAST_VERTEX drops only the newest point', () => {
    const state = reduceAll([
      { type: 'LOAD', slots: [], sourceFrame: FRAME },
      { type: 'ADD_VERTEX', point: { x: 0, y: 0 } },
      { type: 'ADD_VERTEX', point: { x: 10, y: 0 } },
      { type: 'ADD_VERTEX', point: { x: 10, y: 10 } },
      { type: 'REMOVE_LAST_VERTEX' },
    ])

    expect(state.draft).toEqual([
      { x: 0, y: 0 },
      { x: 10, y: 0 },
    ])
  })

  it('clears the draft entirely once the last point is taken back', () => {
    const state = reduceAll([
      { type: 'LOAD', slots: [], sourceFrame: FRAME },
      { type: 'ADD_VERTEX', point: { x: 0, y: 0 } },
      { type: 'REMOVE_LAST_VERTEX' },
    ])

    expect(state.draft).toBeNull()
  })

  it('is a no-op with nothing being drawn, and never touches committed slots', () => {
    const loaded = reduceAll([{ type: 'LOAD', slots: [square('a', 'A1')], sourceFrame: FRAME }])
    const state = roiEditorReducer(loaded, { type: 'REMOVE_LAST_VERTEX' })

    expect(state).toBe(loaded)
  })

  it('does not disturb the slot history, so undo after finishing still works', () => {
    const state = reduceAll([
      { type: 'LOAD', slots: [square('a', 'A1')], sourceFrame: FRAME },
      { type: 'ADD_VERTEX', point: { x: 100, y: 100 } },
      { type: 'ADD_VERTEX', point: { x: 200, y: 100 } },
      { type: 'REMOVE_LAST_VERTEX' },
      { type: 'ADD_VERTEX', point: { x: 300, y: 100 } },
      { type: 'ADD_VERTEX', point: { x: 300, y: 200 } },
      { type: 'CLOSE_DRAFT' },
    ])

    expect(state.slots).toHaveLength(2)
    // One entry: the CLOSE_DRAFT. Point-level edits must not stack up here,
    // or Ctrl+Z after finishing would walk back through vertices instead of
    // removing the slot the operator just made.
    expect(state.history.past).toHaveLength(1)

    const undone = roiEditorReducer(state, { type: 'UNDO' })
    expect(undone.slots).toHaveLength(1)
  })
})
