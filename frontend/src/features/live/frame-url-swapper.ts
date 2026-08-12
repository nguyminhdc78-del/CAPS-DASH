/**
 * Creates a fresh objectURL per frame and revokes the PREVIOUS one - but only
 * once the browser has actually finished loading its replacement.
 *
 * Revoking the outgoing URL any earlier risks a blank flash: some engines
 * re-resolve a still-visible `<img>`'s `src` on repaint, and a URL revoked
 * before its replacement has landed can fail that re-resolve. A throwaway
 * `Image()` is the gate - once it has fired `load` or `error`, the browser is
 * done needing the old bytes, and the caller's `onSwap` fires with the new
 * URL at the same moment, so header state and image state can never drift
 * apart by one frame.
 *
 * Generic over `payload` so the caller (the stream manager) can carry the
 * decoded `FrameHeader` through unchanged, without this module needing to
 * know what a frame header is.
 */
export interface FrameUrlSwapper<Payload> {
  showFrame: (jpeg: Blob, payload: Payload) => void
  /** Revokes whatever URL is still outstanding. Call once, on teardown. */
  dispose: () => void
}

export function createFrameUrlSwapper<Payload>(
  onSwap: (url: string, payload: Payload) => void,
): FrameUrlSwapper<Payload> {
  let currentUrl: string | null = null
  let issued = 0
  let shown = 0

  function showFrame(jpeg: Blob, payload: Payload): void {
    const sequence = ++issued
    const nextUrl = URL.createObjectURL(jpeg)
    const preload = new Image()
    preload.onload = preload.onerror = () => {
      if (sequence <= shown) {
        // A newer frame is already up. Decodes are concurrent and can finish
        // out of order, and without this the older one would take the screen
        // back a frame AND revoke the url the <img> is currently showing,
        // blanking it. Rare at a three-second tick; ordinary at a live one.
        URL.revokeObjectURL(nextUrl)
        return
      }
      shown = sequence
      const previous = currentUrl
      currentUrl = nextUrl
      if (previous) URL.revokeObjectURL(previous)
      onSwap(nextUrl, payload)
    }
    preload.src = nextUrl
  }

  function dispose(): void {
    if (currentUrl) {
      URL.revokeObjectURL(currentUrl)
      currentUrl = null
    }
  }

  return { showFrame, dispose }
}
