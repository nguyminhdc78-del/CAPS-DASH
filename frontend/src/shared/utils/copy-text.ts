/**
 * Copy text to the clipboard, in a page that is not a secure context.
 *
 * `navigator.clipboard` is secure-context only, so it exists on `localhost`
 * during development and is `undefined` the moment the dashboard is served
 * from the board's LAN address over plain HTTP - which is how this product is
 * actually deployed. The same trap took out the ROI editor via
 * `crypto.randomUUID`.
 *
 * The fallback is the old `execCommand('copy')` path: deprecated, still
 * implemented everywhere, and the only thing that works over plain HTTP.
 * Returns whether the copy succeeded so callers can tell the operator to
 * select the text by hand rather than silently doing nothing.
 */
export async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // Permission denied, or a browser that exposes the API and refuses it.
      // Fall through to the legacy path rather than giving up.
    }
  }

  const area = document.createElement('textarea')
  area.value = text
  // Off-screen but still focusable: `execCommand` copies the selection, and a
  // `display: none` element cannot hold one.
  area.style.position = 'fixed'
  area.style.top = '-1000px'
  area.setAttribute('readonly', 'true')
  document.body.appendChild(area)

  try {
    area.select()
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    document.body.removeChild(area)
  }
}
