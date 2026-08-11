import { authTokenStore } from '@/core/api/auth-token-store'
import { refreshAccessToken } from '@/core/api/refresh-single-flight'
import { buildStreamUrl } from './build-stream-url'
import { createFrameUrlSwapper } from './frame-url-swapper'
import { decodeFrameMessage } from './decode-frame-message'
import { classifyClose } from './stream-close-policy'
import { isPingMessage } from './parse-control-message'
import { nextBackoffDelayMs } from './reconnect-backoff'
import type { FrameHeader } from './frame-header-types'

export type StreamStatus =
  | 'connecting'
  | 'authenticating'
  | 'streaming'
  | 'reconnecting'
  | 'paused'
  | 'closed'

export interface StreamManagerCallbacks {
  onStatus: (status: StreamStatus) => void
  /** Fires together with onJpegUrl, for exactly one frame - see frame-url-swapper.ts. */
  onFrame: (header: FrameHeader) => void
  onJpegUrl: (url: string) => void
  onError: (error: { code: string } | null) => void
}

/**
 * Owns exactly one WebSocket's lifetime for one camera.
 *
 * All mutable connection state lives in one plain object rather than a
 * half-dozen refs scattered across a hook body - that is what makes React 19
 * StrictMode's dev-only mount -> cleanup -> mount dance safe: `use-camera-
 * stream.ts` creates exactly one manager per real mount and only ever calls
 * start()/dispose() on it.
 *
 * The generation counter guards a narrower problem than "two sockets open":
 * `close()` is async, so a socket closed during cleanup can still deliver a
 * belated onmessage/onclose. Every handler compares its captured generation
 * against the current one and drops stale callbacks.
 */
export class CameraStreamManager {
  private socket: WebSocket | null = null
  private generation = 0
  private attempt = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private disposed = false
  // True only while idle *because the tab is hidden* - resuming after a
  // terminal policy close (e.g. 'forbidden') would silently undo "do not retry".
  private pausedForVisibility = false

  private readonly swapper = createFrameUrlSwapper<FrameHeader>((url, header) => {
    // Both fire from the same swap, so the overlay (driven by the header)
    // and the image it is drawn over can never describe different frames.
    this.callbacks.onJpegUrl(url)
    this.callbacks.onFrame(header)
  })

  private readonly handleVisibilityChange = (): void => {
    if (this.disposed) return
    if (document.visibilityState === 'hidden') {
      this.pause()
    } else if (this.pausedForVisibility) {
      this.attempt = 0
      this.connect()
    }
  }

  constructor(
    private readonly cameraId: number,
    private readonly callbacks: StreamManagerCallbacks,
  ) {}

  start(): void {
    if (this.disposed) return
    document.addEventListener('visibilitychange', this.handleVisibilityChange)
    if (document.visibilityState === 'hidden') this.pause()
    else this.connect()
  }

  /** Full teardown. Call exactly once, from the owning effect's cleanup. */
  dispose(): void {
    this.disposed = true
    document.removeEventListener('visibilitychange', this.handleVisibilityChange)
    this.clearReconnectTimer()
    this.generation++
    this.socket?.close(1000, 'unmount')
    this.socket = null
    this.swapper.dispose()
  }

  /** Manual retry after a non-retryable close, e.g. "too many viewers". */
  reconnectNow(): void {
    if (this.disposed) return
    this.attempt = 0
    this.connect()
  }

  private pause(): void {
    this.pausedForVisibility = true
    this.clearReconnectTimer()
    this.generation++
    this.socket?.close(1000, 'client_hidden')
    this.socket = null
    this.callbacks.onStatus('paused')
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private connect(): void {
    if (this.disposed) return
    this.pausedForVisibility = false
    const generation = ++this.generation
    this.callbacks.onStatus('connecting')
    this.callbacks.onError(null)

    const socket = new WebSocket(buildStreamUrl(this.cameraId))
    socket.binaryType = 'arraybuffer' // otherwise event.data is a Blob and decodeFrameMessage never runs
    this.socket = socket
    socket.onopen = () => {
      if (generation !== this.generation) {
        socket.close()
        return
      }
      this.callbacks.onStatus('authenticating')
      socket.send(JSON.stringify({ type: 'auth', token: authTokenStore.get() ?? '' }))
    }
    socket.onmessage = (event: MessageEvent<string | ArrayBuffer>) => {
      if (generation !== this.generation) return
      this.handleMessage(event.data)
    }
    socket.onclose = (event: CloseEvent) => {
      if (generation !== this.generation) return
      void this.handleClose(event)
    }
  }

  private handleMessage(data: string | ArrayBuffer): void {
    if (typeof data === 'string') {
      this.handleControlMessage(data)
      return
    }
    try {
      const { header, jpeg } = decodeFrameMessage(data)
      this.attempt = 0 // a real frame landed - any prior backoff escalation is stale
      this.callbacks.onStatus('streaming')
      this.swapper.showFrame(jpeg, header)
    } catch (error) {
      // Malformed frame: dropped, not fatal. The next one is seconds away.
      if (import.meta.env.DEV) console.warn('[live] malformed frame message', error)
    }
  }

  private handleControlMessage(raw: string): void {
    if (isPingMessage(raw)) this.socket?.send(JSON.stringify({ type: 'pong' }))
  }

  private async handleClose(event: CloseEvent): Promise<void> {
    const action = classifyClose(event)
    if (action === 'refresh-and-reconnect') {
      this.callbacks.onStatus('reconnecting')
      const refreshed = await refreshAccessToken()
      if (this.disposed) return
      if (document.visibilityState === 'hidden') {
        // The tab went hidden while the refresh was in flight - hand off to
        // handleVisibilityChange's resume path rather than connecting here.
        this.pausedForVisibility = true
        this.callbacks.onStatus('paused')
        return
      }
      if (!refreshed) {
        this.callbacks.onStatus('closed')
        this.callbacks.onError({ code: 'refresh_failed' })
        return
      }
      this.connect() // immediate: the token, not the network, was the problem
      return
    }

    if (action === 'no-retry') {
      this.callbacks.onStatus('closed')
      this.callbacks.onError({ code: event.reason || 'unknown' })
      return
    }

    const delay = nextBackoffDelayMs(this.attempt)
    this.attempt += 1
    this.callbacks.onStatus('reconnecting')
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }
}
