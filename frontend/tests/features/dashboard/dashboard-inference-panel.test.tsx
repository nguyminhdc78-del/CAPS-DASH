import '@/core/i18n/i18n-config'

import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/core/i18n/i18n-config'
import { DashboardInferencePanel } from '@/features/dashboard/dashboard-inference-panel'
import type { FrameHeader } from '@/features/live/frame-header-types'

function header(seq: number, overrides: Partial<FrameHeader> = {}): FrameHeader {
  return {
    camera_id: 1,
    camera_code: 'demo-01',
    seq,
    captured_at: '2026-08-12T05:00:00Z',
    frame_w: 640,
    frame_h: 480,
    process_ms: 600,
    confidence: 0.35,
    slots: [],
    detections: [],
    ...overrides,
  }
}

/**
 * The panel republishes on a timer rather than on every frame, so these tests
 * drive fake timers forward past one publish tick after feeding frames in.
 * The advance goes inside `act()`: without it React 19 never flushes the
 * state update the interval schedules, and every assertion below fails
 * looking for text the component did compute but had not rendered.
 */
describe('DashboardInferencePanel', () => {
  beforeEach(async () => {
    vi.useFakeTimers()
    await i18n.changeLanguage('en')
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders nothing before any frame has arrived', () => {
    const { container } = render(<DashboardInferencePanel header={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('reports the share of frames the change gate kept YOLO off', () => {
    const { rerender } = render(<DashboardInferencePanel header={header(1)} />)
    // Three skipped frames after the one inferred frame above: 3 of 4.
    for (const seq of [2, 3, 4]) {
      rerender(<DashboardInferencePanel header={header(seq, { inference_skipped: true })} />)
    }
    act(() => vi.advanceTimersByTime(600))

    expect(screen.getByText('75% of frames')).toBeInTheDocument()
  })

  it('counts one sample per frame even when React re-renders with the same header', () => {
    const repeated = header(1, { inference_skipped: true })
    const { rerender } = render(<DashboardInferencePanel header={repeated} />)
    rerender(<DashboardInferencePanel header={repeated} />)
    rerender(<DashboardInferencePanel header={repeated} />)
    rerender(<DashboardInferencePanel header={header(2)} />)
    act(() => vi.advanceTimersByTime(600))

    // Two distinct frames, one skipped - not four samples with three skipped.
    expect(screen.getByText('50% of frames')).toBeInTheDocument()
  })

  it('shows the median inference time of the frames YOLO actually ran on', () => {
    const { rerender } = render(<DashboardInferencePanel header={header(1, { process_ms: 500 })} />)
    rerender(<DashboardInferencePanel header={header(2, { process_ms: 700 })} />)
    // A skipped frame reports process_ms 0 and must not drag the median down.
    rerender(<DashboardInferencePanel header={header(3, { process_ms: 0, inference_skipped: true })} />)
    act(() => vi.advanceTimersByTime(600))

    expect(screen.getByText('Inference 600 ms per run')).toBeInTheDocument()
  })

  it('does not blend one camera’s samples into the next when the operator switches', () => {
    const { rerender } = render(
      <DashboardInferencePanel header={header(1, { inference_skipped: true })} />,
    )
    rerender(<DashboardInferencePanel header={header(2, { inference_skipped: true })} />)
    // Two frames on the new camera, one of them skipped.
    rerender(<DashboardInferencePanel header={header(9, { camera_id: 2 })} />)
    rerender(
      <DashboardInferencePanel header={header(10, { camera_id: 2, inference_skipped: true })} />,
    )
    act(() => vi.advanceTimersByTime(600))

    // 1 of 2 for the new camera. Carrying the previous camera's two skipped
    // frames over would read 3 of 4.
    expect(screen.getByText('50% of frames')).toBeInTheDocument()
  })

  it('reports how many vehicles the detector currently sees', () => {
    const detections = [
      { x1: 0, y1: 0, x2: 10, y2: 10, confidence: 0.9, label: 'car' },
      { x1: 20, y1: 0, x2: 30, y2: 10, confidence: 0.8, label: 'car' },
    ]
    render(<DashboardInferencePanel header={header(1, { detections })} />)
    act(() => vi.advanceTimersByTime(600))

    expect(screen.getByText('Seeing 2 vehicles')).toBeInTheDocument()
  })
})
