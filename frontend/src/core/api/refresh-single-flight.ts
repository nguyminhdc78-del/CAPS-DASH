import { authTokenStore } from './auth-token-store'

/**
 * Refresh the access token, at most once at a time.
 *
 * The dashboard fires several requests at once on page load. When the token
 * has expired they all get a 401 together, and without this every one of them
 * would call /auth/refresh. Since refresh tokens ROTATE, the first call
 * invalidates the token the others are still using - the backend then sees a
 * rotated JTI presented again, correctly reads it as token theft, and revokes
 * every session the user has. The user gets logged out of everything for the
 * crime of loading a page.
 *
 * So: one in-flight refresh, shared by every waiter.
 */

let inFlight: Promise<boolean> | null = null

export function refreshAccessToken(): Promise<boolean> {
  inFlight ??= runRefresh().finally(() => {
    inFlight = null
  })
  return inFlight
}

async function runRefresh(): Promise<boolean> {
  let response: Response
  try {
    response = await fetch('/api/auth/refresh', {
      method: 'POST',
      // Sends the httpOnly refresh cookie. Same-origin because the SPA is
      // served by the same FastAPI app that owns the API.
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
  } catch {
    // Network down. Not an auth failure - keep whatever token we hold so a
    // reconnect can carry on rather than bouncing the user to /login.
    return false
  }

  if (!response.ok) {
    authTokenStore.clear()
    return false
  }

  const body = (await response.json()) as { access_token?: string }
  if (!body.access_token) {
    authTokenStore.clear()
    return false
  }

  authTokenStore.set(body.access_token)
  return true
}

/** Test seam: drop any shared promise between cases. */
export function resetRefreshStateForTests(): void {
  inFlight = null
}
