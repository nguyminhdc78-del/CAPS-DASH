/**
 * The access token lives here: in memory, for the lifetime of the tab.
 *
 * Not localStorage, and not sessionStorage. Anything reachable from JavaScript
 * is reachable from injected JavaScript, and a stored access token turns one
 * XSS into a durable account compromise. The refresh token is held by the
 * browser in an httpOnly cookie the page cannot read at all, so a fresh tab
 * silently recovers a session without the token ever being scriptable.
 *
 * Exported as an object rather than a mutable `let`: live module bindings are
 * easy to import and then accidentally snapshot into a stale local.
 */

let accessToken: string | null = null

export const authTokenStore = {
  get(): string | null {
    return accessToken
  },
  set(token: string): void {
    accessToken = token
  },
  clear(): void {
    accessToken = null
  },
}
