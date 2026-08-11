import '@/core/i18n/i18n-config'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { queryKeys } from '@/core/api/query-keys'
import i18n from '@/core/i18n/i18n-config'
import KioskPage from '@/features/kiosk/kiosk-page'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: '',
    json: () => Promise.resolve(body),
  } as Response
}

const SUMMARY_OK = {
  total: 10,
  free: 6,
  occupied: 3,
  unknown: 1,
  by_floor: [{ floor: '1', total: 10, free: 6, occupied: 3, unknown: 1 }],
  updated_at: '2026-01-01T00:00:00Z',
}

/**
 * The kiosk's one hard requirement: a failed poll must not blank the
 * screen. See `use-kiosk-summary.ts` / `kiosk-offline-banner.tsx` - a
 * stale-but-labelled count is more useful on a lobby display than a
 * spinner, so the last good numbers must stay visible under the banner.
 */
describe('KioskPage', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('keeps showing the last good numbers and adds an offline banner when polling fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(200, SUMMARY_OK))
      .mockResolvedValue(
        jsonResponse(500, { error: { code: 'INTERNAL_ERROR', message: 'boom', request_id: '', details: {} } }),
      )
    vi.stubGlobal('fetch', fetchMock)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <KioskPage />
      </QueryClientProvider>,
    )

    await waitFor(() => {
      expect(within(screen.getByRole('group', { name: 'Free' })).getByText('6')).toBeInTheDocument()
    })
    expect(screen.queryByText('Offline')).not.toBeInTheDocument()

    await queryClient.refetchQueries({ queryKey: queryKeys.summary() })

    await waitFor(() => {
      expect(screen.getByText('Offline')).toBeInTheDocument()
    })
    // The numbers from the last successful poll are still on screen.
    expect(within(screen.getByRole('group', { name: 'Free' })).getByText('6')).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Occupied' })).getByText('3')).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Unknown' })).getByText('1')).toBeInTheDocument()
  })
})
