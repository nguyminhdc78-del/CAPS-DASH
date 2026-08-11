import '@/core/i18n/i18n-config'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/core/i18n/i18n-config'
import { CameraConnectionTest } from '@/features/cameras/camera-connection-test'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: '',
    json: () => Promise.resolve(body),
  } as Response
}

/**
 * The endpoint answers HTTP 200 with `{ ok: false, error_code, ... }` for a
 * genuine connection failure - that is a normal diagnostic result, not an
 * exception. These tests pin down both halves of that contract: `ok:false`
 * must render inline without throwing, and `ok:true` must show the probe's
 * numbers.
 */
describe('CameraConnectionTest', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('renders the localized error and does not throw when ok:false', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(200, {
          ok: false,
          latency_ms: 12,
          frame_width: 0,
          frame_height: 0,
          error: 'connection refused',
          error_code: 'CAMERA_UNREACHABLE',
        }),
      ),
    )

    expect(() =>
      render(
        <CameraConnectionTest
          cameraId={null}
          sourceType="esp32cam_http"
          sourceUrl="http://10.0.0.5/capture"
        />,
      ),
    ).not.toThrow()

    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))

    await waitFor(() => {
      expect(screen.getByText('Connection failed')).toBeInTheDocument()
    })
    // Localized from the error CODE via errors.json, not the raw dev message.
    expect(screen.getByText('Cannot reach the camera.')).toBeInTheDocument()
    expect(screen.queryByText('connection refused')).not.toBeInTheDocument()
  })

  it('renders latency and frame size when ok:true', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(200, {
          ok: true,
          latency_ms: 42,
          frame_width: 640,
          frame_height: 480,
          error: '',
          error_code: '',
        }),
      ),
    )

    render(<CameraConnectionTest cameraId={7} sourceType="esp32cam_http" sourceUrl="" />)

    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))

    await waitFor(() => {
      expect(screen.getByText('Connection succeeded')).toBeInTheDocument()
    })
    expect(screen.getByText('42 ms')).toBeInTheDocument()
    expect(screen.getByText('640 x 480')).toBeInTheDocument()
  })
})
