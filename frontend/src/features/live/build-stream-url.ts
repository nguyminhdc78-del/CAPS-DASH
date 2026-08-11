/**
 * Same-origin, derived from `location` - never a second, configurable host.
 *
 * A live-view feed pointed at its own base URL is exactly the drift the
 * backend design review flagged (scout anti-pattern #13): one more setting to
 * get out of sync with the API host, and one more thing that breaks the
 * moment this app is served from somewhere else. Deriving it structurally
 * rules that out.
 */
export function buildStreamUrl(cameraId: number): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/cameras/${cameraId}`
}
