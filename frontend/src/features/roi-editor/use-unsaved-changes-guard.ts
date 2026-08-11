import { useEffect } from 'react'
import { useBlocker } from 'react-router'
import type { Blocker } from 'react-router'

/**
 * Two separate guards for two separate ways to leave with unsaved work:
 *   - in-app navigation (sidebar, browser back) -> react-router's data-router
 *     `useBlocker`, which lets the page render its own confirm Modal
 *     (`blocker.state === 'blocked'`, resolved via `blocker.proceed()` /
 *     `blocker.reset()`).
 *   - tab close / refresh -> `beforeunload`, which no Modal can intercept;
 *     the browser's own native dialog is the only option there.
 */
export function useUnsavedChangesGuard(dirty: boolean): Blocker {
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname,
  )

  useEffect(() => {
    if (!dirty) return
    const handler = (event: BeforeUnloadEvent): void => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])

  return blocker
}
