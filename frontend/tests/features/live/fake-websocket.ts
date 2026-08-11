/**
 * Minimal WebSocket stand-in for tests. Not a `.test.ts` file on purpose -
 * vitest's `include` glob only picks up `*.test.{ts,tsx}`, so this shared
 * helper does not get collected as a suite of its own.
 */
export class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  static reset(): void {
    FakeWebSocket.instances = []
  }

  binaryType = 'blob'
  closed = false
  closeCode: number | null = null
  closeReason = ''
  sentMessages: string[] = []

  onopen: (() => void) | null = null
  onmessage: ((event: { data: string | ArrayBuffer }) => void) | null = null
  onclose: ((event: { code: number; reason: string }) => void) | null = null
  onerror: (() => void) | null = null

  constructor(public readonly url: string) {
    FakeWebSocket.instances.push(this)
  }

  send(data: string): void {
    this.sentMessages.push(data)
  }

  /** Client-initiated close, mirroring the real WebSocket.close() contract. */
  close(code = 1000, reason = ''): void {
    if (this.closed) return
    this.closed = true
    this.closeCode = code
    this.closeReason = reason
    this.onclose?.({ code, reason })
  }

  // --- test-only helpers, not part of the real WebSocket API ---

  simulateOpen(): void {
    this.onopen?.()
  }

  simulateMessage(data: string | ArrayBuffer): void {
    this.onmessage?.({ data })
  }

  /** Server-initiated close (e.g. a 1008 policy close). */
  simulateServerClose(code: number, reason: string): void {
    if (this.closed) return
    this.closed = true
    this.closeCode = code
    this.closeReason = reason
    this.onclose?.({ code, reason })
  }
}
