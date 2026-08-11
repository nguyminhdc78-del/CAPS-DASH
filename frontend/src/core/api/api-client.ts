import { ApiError, apiErrorFromResponse } from './api-error'
import { authTokenStore } from './auth-token-store'
import { refreshAccessToken } from './refresh-single-flight'

/**
 * The one way this app talks to the backend.
 *
 * Single origin, always: the API is served by the same FastAPI process as the
 * SPA, so there is no configurable host and no cross-origin credential dance.
 */

const AUTH_EXPIRED_EVENT = 'caps:auth-expired'

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  /** Internal: prevents an infinite refresh/retry loop. */
  retryOnUnauthorized?: boolean
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, retryOnUnauthorized = true, ...init } = options

  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')

  const token = authTokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  if (body !== undefined) headers.set('Content-Type', 'application/json')

  const response = await fetch(`/api${path}`, {
    ...init,
    headers,
    credentials: 'same-origin',
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })

  if (response.status === 401 && retryOnUnauthorized) {
    // Expired access token is the common case and must be invisible to the
    // user. Refresh once, replay once. If refresh fails the session is really
    // over, and the app - not this function - decides what to show.
    if (await refreshAccessToken()) {
      return apiRequest<T>(path, { ...options, retryOnUnauthorized: false })
    }
    emitAuthExpired()
    throw await apiErrorFromResponse(response)
  }

  if (!response.ok) throw await apiErrorFromResponse(response)

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'POST', body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'PUT', body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'PATCH', body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'DELETE' }),
}

/**
 * Announce that the session is gone.
 *
 * An event rather than a mutable global: the auth provider subscribes and
 * clears its own state, so there is no module that both the API layer and
 * React write to.
 */
function emitAuthExpired(): void {
  window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT))
}

export function onAuthExpired(handler: () => void): () => void {
  window.addEventListener(AUTH_EXPIRED_EVENT, handler)
  return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handler)
}

export { ApiError }
