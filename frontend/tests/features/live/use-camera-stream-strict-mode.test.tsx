import { StrictMode } from 'react'
import { act, cleanup, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useCameraStream } from '@/features/live/use-camera-stream'
import { FakeWebSocket } from './fake-websocket'

vi.stubGlobal('WebSocket', FakeWebSocket)

function Probe({ cameraId }: { cameraId: number }): null {
  useCameraStream(cameraId)
  return null
}

describe('useCameraStream under React 19 StrictMode', () => {
  beforeEach(() => {
    FakeWebSocket.reset()
  })

  afterEach(() => {
    cleanup()
  })

  it('leaves exactly one socket open after the dev mount -> cleanup -> mount dance', () => {
    act(() => {
      render(
        <StrictMode>
          <Probe cameraId={1} />
        </StrictMode>,
      )
    })

    // StrictMode may well have constructed a throwaway socket for the first,
    // immediately-cleaned-up effect run - that is expected. What must never
    // happen is two live sockets left open, each holding a viewer slot.
    const openSockets = FakeWebSocket.instances.filter((socket) => !socket.closed)
    expect(openSockets).toHaveLength(1)
  })

  it('closes the socket on unmount, leaving none open', () => {
    let unmount: (() => void) | undefined
    act(() => {
      const result = render(
        <StrictMode>
          <Probe cameraId={1} />
        </StrictMode>,
      )
      unmount = result.unmount
    })

    act(() => {
      unmount?.()
    })

    const openSockets = FakeWebSocket.instances.filter((socket) => !socket.closed)
    expect(openSockets).toHaveLength(0)
  })
})
