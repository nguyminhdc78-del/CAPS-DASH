import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/core/api/refresh-single-flight', () => ({
  refreshAccessToken: vi.fn(),
}))

import { refreshAccessToken } from '@/core/api/refresh-single-flight'
import { CameraStreamManager } from '@/features/live/camera-stream-manager'
import type { StreamManagerCallbacks, StreamStatus } from '@/features/live/camera-stream-manager'
import { FakeWebSocket } from './fake-websocket'

vi.stubGlobal('WebSocket', FakeWebSocket)

function makeCallbacks(): StreamManagerCallbacks & {
  statuses: StreamStatus[]
  errors: Array<{ code: string } | null>
} {
  const statuses: StreamStatus[] = []
  const errors: Array<{ code: string } | null> = []
  return {
    statuses,
    errors,
    onStatus: (status) => statuses.push(status),
    onFrame: () => {},
    onJpegUrl: () => {},
    onError: (error) => errors.push(error),
  }
}

describe('CameraStreamManager close handling', () => {
  beforeEach(() => {
    FakeWebSocket.reset()
    vi.mocked(refreshAccessToken).mockReset()
  })

  it('refreshes the token and reconnects immediately after a token_expired close', async () => {
    vi.mocked(refreshAccessToken).mockResolvedValue(true)
    const callbacks = makeCallbacks()
    const manager = new CameraStreamManager(1, callbacks)

    manager.start()
    expect(FakeWebSocket.instances).toHaveLength(1)

    FakeWebSocket.instances[0]!.simulateServerClose(1008, 'token_expired')
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(2))

    expect(refreshAccessToken).toHaveBeenCalledTimes(1)
    expect(callbacks.statuses.at(-1)).not.toBe('closed')
    expect(callbacks.errors).not.toContainEqual({ code: 'token_expired' })

    manager.dispose()
  })

  it('does not retry after a forbidden close and surfaces the reason', async () => {
    const callbacks = makeCallbacks()
    const manager = new CameraStreamManager(1, callbacks)

    manager.start()
    FakeWebSocket.instances[0]!.simulateServerClose(1008, 'forbidden')

    // Give any (incorrect) async reconnection a turn to happen before asserting.
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(callbacks.statuses.at(-1)).toBe('closed')
    expect(callbacks.errors.at(-1)).toEqual({ code: 'forbidden' })
    expect(refreshAccessToken).not.toHaveBeenCalled()

    manager.dispose()
  })

  it('backs off and retries after a heartbeat_lost close', async () => {
    vi.useFakeTimers()
    const callbacks = makeCallbacks()
    const manager = new CameraStreamManager(1, callbacks)

    manager.start()
    FakeWebSocket.instances[0]!.simulateServerClose(1001, 'heartbeat_lost')

    expect(callbacks.statuses.at(-1)).toBe('reconnecting')
    expect(FakeWebSocket.instances).toHaveLength(1) // not yet - waiting on the backoff timer

    await vi.advanceTimersByTimeAsync(8000)
    expect(FakeWebSocket.instances).toHaveLength(2)

    manager.dispose()
    vi.useRealTimers()
  })
})
