import { lazy } from 'react'
import type { ComponentType, LazyExoticComponent } from 'react'

/** One-shot guard key: set just before a self-heal reload, cleared on any
 *  successful chunk load, so a genuine failure (offline, real 5xx) can never
 *  loop the page. */
const RELOAD_GUARD_KEY = 'caps:chunk-reload'

/** Force a single hard reload, unless we already tried one this session. */
function reloadOnceForStaleChunks(): Promise<never> {
  if (sessionStorage.getItem(RELOAD_GUARD_KEY) === null) {
    sessionStorage.setItem(RELOAD_GUARD_KEY, String(Date.now()))
    window.location.reload()
    // Never resolves: nothing should render in the instant before the reload.
    return new Promise<never>(() => {})
  }
  // A reload already happened and the import still failed - stop, and let the
  // real error surface to the router's error boundary.
  return Promise.reject(new Error('dynamic import failed after reload'))
}

/**
 * `React.lazy`, hardened against the one failure mode a hashed-chunk SPA hits
 * in production: a redeploy changes chunk filenames while a tab is still open
 * on the old `index.html`, so the old filename 404s and the naked `lazy()`
 * dead-ends at "Failed to fetch dynamically imported module".
 *
 * The fresh `index.html` already lists the new names, so a single hard reload
 * self-heals the tab. We reload once (guarded against a loop), and clear the
 * guard on any successful load so a later redeploy can heal again.
 */
export function lazyWithReload<T extends ComponentType<unknown>>(
  factory: () => Promise<{ default: T }>,
): LazyExoticComponent<T> {
  return lazy(() =>
    factory()
      .then((module) => {
        sessionStorage.removeItem(RELOAD_GUARD_KEY)
        return module
      })
      .catch(() => reloadOnceForStaleChunks()),
  )
}
