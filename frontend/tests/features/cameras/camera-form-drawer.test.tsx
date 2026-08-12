import '@/core/i18n/i18n-config'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { App as AntApp } from 'antd'
import { beforeEach, describe, expect, it } from 'vitest'

import i18n from '@/core/i18n/i18n-config'
import { CameraFormDrawer } from '@/features/cameras/camera-form-drawer'
import type { CameraRecord } from '@/features/cameras/use-cameras-queries'

/**
 * The poll interval is the live-view frame rate *and* the inference cadence,
 * so which number lands in this field is not cosmetic. Two rules are pinned
 * here: a new camera takes its source type's default, and an existing one
 * keeps whatever it was tuned to.
 */

// antd's `Select` measures its dropdown via `@rc-component/resize-observer`,
// which throws in jsdom without a `ResizeObserver` global. Stubbed here (this
// file only), matching `tests/features/history/history-date-range.test.tsx`.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
window.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver

const TUNED_CAMERA: CameraRecord = {
  id: 7,
  code: 'CAM-1',
  name: 'Front gate',
  floor: 'B1',
  source_type: 'esp32cam_http',
  // Deliberately not any source type's default: if this value survives, it
  // survived because it was stored, not by coincidence.
  poll_interval_s: 4.5,
  source_url: 'http://10.0.0.5',
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

function renderDrawer(camera: CameraRecord | null): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <AntApp>
        <CameraFormDrawer open camera={camera} onClose={() => {}} />
      </AntApp>
    </QueryClientProvider>,
  )
}

function pollInterval(): number {
  const field = screen.getByRole('spinbutton', { name: /poll interval/i }) as HTMLInputElement
  // As a number, not the raw string: antd's InputNumber reformats to its
  // step's precision ("2" becomes "2.0"), which is display, not value.
  return Number(field.value)
}

async function selectSourceType(label: string): Promise<void> {
  fireEvent.mouseDown(screen.getByRole('combobox', { name: /source type/i }))
  const option = await screen.findByTitle(label)
  fireEvent.click(option)
}

describe('CameraFormDrawer poll interval defaults', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('starts a new polled camera at 2 s', async () => {
    renderDrawer(null)
    await waitFor(() => expect(pollInterval()).toBe(2))
  })

  it('switches a new camera to 0.2 s when the source type becomes a stream', async () => {
    renderDrawer(null)
    await waitFor(() => expect(pollInterval()).toBe(2))

    await selectSourceType('RTSP camera')

    // A stream reads the newest already-decoded frame from memory, so a tick
    // costs almost nothing and 0.2 s keeps the picture live.
    await waitFor(() => expect(pollInterval()).toBe(0.2))
  })

  it('shows an existing camera its stored interval, not the new default', async () => {
    renderDrawer(TUNED_CAMERA)
    await waitFor(() => expect(pollInterval()).toBe(4.5))
  })

  it('does not retune an existing camera when its source type changes', async () => {
    // The documented RTSP rollback is exactly this: switch the camera row back
    // to `rtsp`. If that silently rewrote the interval, an operator following
    // the runbook would retune a live camera by 10x without touching the field.
    renderDrawer(TUNED_CAMERA)
    await waitFor(() => expect(pollInterval()).toBe(4.5))

    await selectSourceType('RTSP camera')

    await waitFor(() => expect(pollInterval()).toBe(4.5))
  })
})
