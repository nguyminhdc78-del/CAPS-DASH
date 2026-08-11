import '@/core/i18n/i18n-config'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { App as AntApp } from 'antd'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/core/i18n/i18n-config'
import HistoryPage from '@/features/history/history-page'

// antd's `RangePicker` measures its popup via `@rc-component/resize-observer`,
// which throws in jsdom without a `ResizeObserver` global. Stubbed here
// (this file only) rather than in the shared `setup-tests.ts` - see the
// identical stub and rationale in
// `tests/features/statistics/occupancy-line-chart.test.tsx`.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
window.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: '',
    json: () => Promise.resolve(body),
  } as Response
}

const EMPTY_PAGE = { items: [], total: 0, limit: 50, offset: 0 }
const EMPTY_OPTIONS = { items: [], total: 0 }

function renderHistoryPage(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <AntApp>
        <HistoryPage />
      </AntApp>
    </QueryClientProvider>,
  )
}

/**
 * `/history` requires a date range and rejects one wider than the server's
 * cap with `RANGE_TOO_WIDE` (see `history_service.resolve_range`). This
 * pins down both ends: the page must send a default range on first load
 * (never an empty `from`/`to`, which the server would reject as
 * `RANGE_INVALID`/422 for a different reason), and a `RANGE_TOO_WIDE`
 * response must surface as the translated sentence from `errors.json`, not
 * a crash or a raw error code on screen.
 */
describe('HistoryPage date range', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('requests /history with a non-empty default from/to on first load', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/history?')) return Promise.resolve(jsonResponse(200, EMPTY_PAGE))
      return Promise.resolve(jsonResponse(200, EMPTY_OPTIONS))
    })
    vi.stubGlobal('fetch', fetchMock)

    renderHistoryPage()

    await waitFor(() => {
      const historyCall = fetchMock.mock.calls.find((call) => String(call[0]).includes('/api/history?'))
      expect(historyCall).toBeDefined()
    })

    const historyCall = fetchMock.mock.calls.find((call) => String(call[0]).includes('/api/history?'))
    const url = new URL(String(historyCall?.[0]), 'http://localhost')
    // Both params are present and parseable - never sent blank, which is
    // what would happen if the picker's default state were left unset.
    expect(url.searchParams.get('from')).toBeTruthy()
    expect(url.searchParams.get('to')).toBeTruthy()
    expect(Number.isNaN(Date.parse(url.searchParams.get('from') ?? ''))).toBe(false)
    expect(Number.isNaN(Date.parse(url.searchParams.get('to') ?? ''))).toBe(false)
  })

  it('surfaces RANGE_TOO_WIDE as the readable errors.json message, not a crash', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/history?')) {
        return Promise.resolve(
          jsonResponse(422, {
            error: {
              code: 'RANGE_TOO_WIDE',
              message: 'Range exceeds the 92-day maximum',
              request_id: 'req-1',
              details: {},
            },
          }),
        )
      }
      return Promise.resolve(jsonResponse(200, EMPTY_OPTIONS))
    })
    vi.stubGlobal('fetch', fetchMock)

    expect(() => renderHistoryPage()).not.toThrow()

    await waitFor(() => {
      // From locales/en/errors.json, keyed off the code - never the raw
      // developer-facing "message" field from the response body.
      expect(screen.getByText('That date range is too wide. Choose a shorter period.')).toBeInTheDocument()
    })
    expect(screen.queryByText('Range exceeds the 92-day maximum')).not.toBeInTheDocument()
  })
})
