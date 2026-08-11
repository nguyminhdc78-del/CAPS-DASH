import type { FrameSize, Point } from './coordinate-transform'

/**
 * Shared shapes for the reducer and every component that reads its state.
 * Split out of `use-roi-editor-state.ts` so components can import types
 * without pulling in reducer logic, and so the reducer file stays under the
 * 200-line cap.
 */

/** One drawn slot. `points` are ALWAYS source-frame pixels - the Konva
 * boundary (roi-slot-polygon.tsx) is the only place that converts. */
export interface EditorSlot {
  /** Stable client-side identity, independent of `code` so renaming a slot
   * never loses its selection, its place in history, or its identity in the
   * save diff. */
  key: string
  code: string
  floor: string
  points: Point[]
}

export interface EditorSelection {
  slotKey: string
  /** null = the whole polygon is selected (drag/delete-slot); a number = one
   * vertex is selected (Del removes just that vertex). */
  vertexIndex: number | null
}

export type EditorMode = 'select' | 'draw' | 'pan'

export interface HistoryState {
  past: EditorSlot[][]
  future: EditorSlot[][]
}

export interface RoiEditorState {
  slots: EditorSlot[]
  /** Vertices of the polygon currently being drawn, or null when not drawing. */
  draft: Point[] | null
  selection: EditorSelection | null
  history: HistoryState
  /** Last loaded/saved slots. Used for the dirty flag and the save-confirm
   * diff (added/modified/removed codes) - not part of undo history, which
   * tracks in-session edits, not "distance from the server". */
  baseline: EditorSlot[]
  dirty: boolean
  /** The frame every point in `slots`/`draft` is expressed against. Set by LOAD. */
  sourceFrame: FrameSize | null
}
