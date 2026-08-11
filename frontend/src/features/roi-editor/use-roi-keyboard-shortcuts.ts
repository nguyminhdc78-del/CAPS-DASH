import { useEffect, useRef } from 'react'

/** See the on-screen help popover (roi-editor-help-popover.tsx) for the
 * user-facing list; keep the two in sync when adding a shortcut here. */
export interface RoiKeyboardHandlers {
  onUndo: () => void
  onRedo: () => void
  onDeleteSelected: () => void
  onCloseDraft: () => void
  onCancelDraft: () => void
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  // Del must not fire while renaming a slot's code/floor in an <Input>, and
  // Ctrl+Z should undo the operator's typing there via the browser's native
  // input undo, not a vertex somewhere on the canvas.
  return tag === 'INPUT' || tag === 'TEXTAREA' || target.isContentEditable
}

export function useRoiKeyboardShortcuts(handlers: RoiKeyboardHandlers): void {
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (isTypingTarget(event.target)) return
      const h = handlersRef.current
      const ctrlLike = event.ctrlKey || event.metaKey
      const key = event.key.toLowerCase()

      if (ctrlLike && key === 'z' && event.shiftKey) {
        event.preventDefault()
        h.onRedo()
        return
      }
      if (ctrlLike && key === 'z') {
        event.preventDefault()
        h.onUndo()
        return
      }
      if (ctrlLike && key === 'y') {
        event.preventDefault()
        h.onRedo()
        return
      }
      if (event.key === 'Delete' || event.key === 'Backspace') {
        h.onDeleteSelected()
        return
      }
      if (event.key === 'Enter') {
        h.onCloseDraft()
        return
      }
      if (event.key === 'Escape') {
        h.onCancelDraft()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])
}
