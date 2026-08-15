import '@/core/i18n/i18n-config'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { App as AntApp } from 'antd'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthContext } from '@/core/auth/auth-context'
import type { CurrentUser } from '@/core/auth/auth-context'
import i18n from '@/core/i18n/i18n-config'
import { CameraSettingsDrawer } from '@/features/cameras/camera-settings-drawer'
import type { CameraRecord } from '@/features/cameras/use-cameras-queries'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: '',
    json: () => Promise.resolve(body),
  } as Response
}

const CAMERA: CameraRecord = {
  id: 7,
  code: 'CAM-1',
  name: 'Front gate',
  floor: 'B1',
  source_type: 'esp32cam_http',
  source_url: 'http://10.0.0.5',
  poll_interval_s: 3,
  vote_window: 5,
  vote_threshold: 4,
  confidence: 0.25,
  is_enabled: true,
  frame_width: 640,
  frame_height: 480,
  last_seen_at: null,
  last_error: '',
  slot_count: 0,
  health: null,
}

const REPORTED_SETTINGS = {
  brightness: 0,
  contrast: 0,
  saturation: 0,
  quality: 12,
  aec: 1,
  agc: 1,
  awb: 1,
  hmirror: 0,
  vflip: 0,
  led: 0,
  rssi: -55,
}

function userWithRole(role: CurrentUser['role']): CurrentUser {
  return { username: role, display_name: role, role }
}

function renderDrawer(role: CurrentUser['role']): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const authValue = {
    user: userWithRole(role),
    status: 'authenticated' as const,
    login: vi.fn(),
    logout: vi.fn(),
  }
  render(
    <QueryClientProvider client={queryClient}>
      <AntApp>
        <AuthContext value={authValue}>
          <CameraSettingsDrawer open camera={CAMERA} onClose={() => {}} />
        </AuthContext>
      </AntApp>
    </QueryClientProvider>,
  )
}

/**
 * The exposure lock is the panel's central control (see
 * `camera-exposure-lock.tsx`'s docstring for why), so its wiring to the
 * `lock_exposure` field - not the three raw flags individually - is pinned
 * down directly rather than trusted to work because the sliders do.
 */
describe('CameraSettingsDrawer', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('sends lock_exposure when the exposure-lock switch is toggled', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(200, { camera_id: 7, settings: REPORTED_SETTINGS, applied: null }))
      .mockResolvedValueOnce(
        jsonResponse(200, {
          camera_id: 7,
          settings: { ...REPORTED_SETTINGS, aec: 0, agc: 0, awb: 0 },
          applied: { aec: true, agc: true, awb: true },
        }),
      )
      .mockResolvedValue(
        jsonResponse(200, { camera_id: 7, settings: { ...REPORTED_SETTINGS, aec: 0, agc: 0, awb: 0 }, applied: null }),
      )
    vi.stubGlobal('fetch', fetchMock)

    renderDrawer('admin')

    const lockSwitch = await screen.findByRole('switch', { name: 'Lock exposure' })
    fireEvent.click(lockSwitch)

    // The success path also invalidates the GET query, which refetches -
    // asserting a fixed call count would be timing-dependent, so the PATCH
    // call is found by its method instead of its position.
    await waitFor(() => {
      const patchCalls = fetchMock.mock.calls.filter(
        (call) => (call[1] as RequestInit | undefined)?.method === 'PATCH',
      )
      expect(patchCalls).toHaveLength(1)
    })
    const patchCall = fetchMock.mock.calls.find(
      (call) => (call[1] as RequestInit | undefined)?.method === 'PATCH',
    ) as [string, RequestInit]
    expect(patchCall[0]).toBe('/api/cameras/7/settings')
    expect(JSON.parse(String(patchCall[1].body))).toEqual({ lock_exposure: true })
  })

  it('surfaces a device-rejected field from `applied` after a write', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(200, { camera_id: 7, settings: REPORTED_SETTINGS, applied: null }))
      .mockResolvedValueOnce(
        jsonResponse(200, {
          camera_id: 7,
          settings: { ...REPORTED_SETTINGS, hmirror: 0 },
          applied: { hmirror: false },
        }),
      )
      .mockResolvedValue(jsonResponse(200, { camera_id: 7, settings: REPORTED_SETTINGS, applied: null }))
    vi.stubGlobal('fetch', fetchMock)

    renderDrawer('admin')

    const hmirrorSwitch = await screen.findByRole('switch', { name: 'Horizontal mirror' })
    fireEvent.click(hmirrorSwitch)

    await waitFor(() => {
      expect(screen.getByText('The device rejected: hmirror.')).toBeInTheDocument()
    })
  })

  it('disables every control for a non-admin viewer, with a stated reason', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { camera_id: 7, settings: REPORTED_SETTINGS, applied: null }))
    vi.stubGlobal('fetch', fetchMock)

    renderDrawer('security')

    await screen.findByRole('switch', { name: 'Lock exposure' })
    expect(screen.getByText(/Only administrators can change sensor settings/)).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Lock exposure' })).toBeDisabled()
    expect(screen.getByRole('switch', { name: 'Horizontal mirror' })).toBeDisabled()
    expect(screen.getByRole('switch', { name: 'Vertical flip' })).toBeDisabled()
    expect(screen.getByRole('switch', { name: 'Flash LED' })).toBeDisabled()
  })

  it('renders the no-sensor state for CAMERA_SOURCE_INVALID instead of an error toast', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(422, {
        error: {
          code: 'CAMERA_SOURCE_INVALID',
          message: 'Camera CAM-1 has no controllable sensor',
          request_id: 'req-1',
          details: {},
        },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    renderDrawer('admin')

    await waitFor(() => {
      expect(screen.getByText('This source has no adjustable sensor.')).toBeInTheDocument()
    })
    // The generic, code-mapped error text must not appear - this is a plain
    // state, not the usual error-toast pipeline.
    expect(screen.queryByText(/is not valid for this source type/)).not.toBeInTheDocument()
    expect(screen.queryByRole('switch', { name: 'Lock exposure' })).not.toBeInTheDocument()
  })

  /**
   * Regression. The ring test was first written inside the sensor panel, so a
   * camera whose `/settings` call failed - which is every device without a
   * controllable sensor, and every one that is simply not answering - rendered
   * an error and nothing else. That hides the control at exactly the moment it
   * earns its keep: an installer at a half-working node working out which part
   * is wrong. The ring is a separate device on a separate endpoint and must
   * not share the sensor's fate.
   */
  it('offers the LED ring test even when the sensor cannot be read', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(502, {
        error: {
          code: 'CAMERA_UNREACHABLE',
          message: 'Camera did not report its settings',
          request_id: 'req-2',
          details: {},
        },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    renderDrawer('admin')

    expect(await screen.findByRole('button', { name: 'Occupied (red)' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Free (green)' })).toBeEnabled()
  })

  it('sends the pattern the pressed swatch stands for', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(200, { camera_id: 7, settings: REPORTED_SETTINGS, applied: null }))
      .mockResolvedValue(jsonResponse(200, { camera_id: 7, slots: '1', reverts_within_s: 15 }))
    vi.stubGlobal('fetch', fetchMock)

    renderDrawer('admin')

    fireEvent.click(await screen.findByRole('button', { name: 'Occupied (red)' }))

    await waitFor(() => {
      const posted = fetchMock.mock.calls.find(
        (call) => (call[1] as RequestInit | undefined)?.method === 'POST',
      ) as [string, RequestInit] | undefined
      expect(posted?.[0]).toBe('/api/cameras/7/ring-test')
      expect(JSON.parse(String(posted?.[1].body))).toEqual({ slots: '1' })
    })
  })
})
