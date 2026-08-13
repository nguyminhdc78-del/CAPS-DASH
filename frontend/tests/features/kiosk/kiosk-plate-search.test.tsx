import '@/core/i18n/i18n-config'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { KIOSK_SEARCH_CLEAR_MS } from '@/core/constants/ui-constants'
import i18n from '@/core/i18n/i18n-config'
import { KioskPlateSearch } from '@/features/kiosk/kiosk-plate-search'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: '',
    json: () => Promise.resolve(body),
  } as Response
}

const SEARCH_RESULT = {
  query: '30H83231',
  matches: [
    {
      plate: '30H83231',
      slot_code: 'A1',
      floor: 'B1',
      read_at: '2026-08-13T00:00:00Z',
    },
  ],
}

describe('KioskPlateSearch', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('typing does not fire a fetch', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <KioskPlateSearch />
      </QueryClientProvider>,
    )

    const searchInput = screen.getByRole('searchbox') as HTMLInputElement
    fireEvent.change(searchInput, { target: { value: '30H83231' } })

    // No fetch should have been called just from typing
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('pressing Enter fires exactly one fetch', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, SEARCH_RESULT))
    vi.stubGlobal('fetch', fetchMock)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <KioskPlateSearch />
      </QueryClientProvider>,
    )

    const searchInput = screen.getByRole('searchbox') as HTMLInputElement
    fireEvent.change(searchInput, { target: { value: '30H83231' } })
    fireEvent.keyDown(searchInput, { key: 'Enter' })

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })
  })

  it('shows the bay code and formatted plate in results', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, SEARCH_RESULT))
    vi.stubGlobal('fetch', fetchMock)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <KioskPlateSearch />
      </QueryClientProvider>,
    )

    const searchInput = screen.getByRole('searchbox') as HTMLInputElement
    fireEvent.change(searchInput, { target: { value: '30H83231' } })
    fireEvent.keyDown(searchInput, { key: 'Enter' })

    await waitFor(() => {
      expect(screen.getByText('A1')).toBeInTheDocument()
    })
    // The plate is rendered through `formatPlateForDisplay`, so the customer
    // reads `30H-832.31`, not the raw `30H83231` the API returned.
    expect(screen.getByText('30H-832.31')).toBeInTheDocument()
  })

  it('never exposes camera code or confidence in the result', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, SEARCH_RESULT))
    vi.stubGlobal('fetch', fetchMock)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <KioskPlateSearch />
      </QueryClientProvider>,
    )

    const searchInput = screen.getByRole('searchbox') as HTMLInputElement
    fireEvent.change(searchInput, { target: { value: '30H83231' } })
    fireEvent.keyDown(searchInput, { key: 'Enter' })

    await waitFor(() => {
      expect(screen.getByText('A1')).toBeInTheDocument()
    })

    // Camera code and confidence should never appear
    expect(screen.queryByText(/CAM-1/)).not.toBeInTheDocument()
    expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/0\.\d+/)).not.toBeInTheDocument()
  })

  it('auto-clears the result after KIOSK_SEARCH_CLEAR_MS with fake timers', async () => {
    // `shouldAdvanceTime` keeps the real clock ticking underneath the fake one.
    // Without it `waitFor` - which polls on a timer - can never resolve while
    // timers are faked, and the test dies on its 5 s budget instead of
    // exercising the auto-clear.
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, SEARCH_RESULT))
      vi.stubGlobal('fetch', fetchMock)

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

      render(
        <QueryClientProvider client={queryClient}>
          <KioskPlateSearch />
        </QueryClientProvider>,
      )

      const searchInput = screen.getByRole('searchbox') as HTMLInputElement
      fireEvent.change(searchInput, { target: { value: '30H83231' } })
      fireEvent.keyDown(searchInput, { key: 'Enter' })

      await waitFor(() => {
        expect(screen.getByText('A1')).toBeInTheDocument()
      })

      // Advance past the auto-clear timeout
      vi.advanceTimersByTime(KIOSK_SEARCH_CLEAR_MS + 100)

      // Result should be gone
      await waitFor(() => {
        expect(screen.queryByText('A1')).not.toBeInTheDocument()
      })
    } finally {
      vi.useRealTimers()
    }
  })

  it('renders the localized rate-limit message on 429', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(429, {
        error: {
          code: 'RATE_LIMITED',
          message: 'Rate limited',
          request_id: 'test-id',
          details: { retry_after_s: 60 },
        },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <KioskPlateSearch />
      </QueryClientProvider>,
    )

    const searchInput = screen.getByRole('searchbox') as HTMLInputElement
    fireEvent.change(searchInput, { target: { value: '30H83231' } })
    fireEvent.keyDown(searchInput, { key: 'Enter' })

    // Asserted on the rendered text of `kiosk:rateLimited`, not on
    // `getByRole('alert')`: antd's Alert does not set that ARIA role, so a
    // role query finds nothing and the test dies on its timeout rather than
    // on the thing it means to check. The interpolated retry seconds prove
    // the value came from the 429 body and is not a hardcoded string.
    await waitFor(() => {
      expect(
        screen.getByText('Too many searches. Please wait 60s and try again.'),
      ).toBeInTheDocument()
    })
  })
})
