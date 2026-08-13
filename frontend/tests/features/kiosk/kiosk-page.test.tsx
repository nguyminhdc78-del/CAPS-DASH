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

// Phase 03: the kiosk now polls the public, unauthenticated
// `/public/summary` endpoint (`use-kiosk-summary.ts`), whose response
// wraps the old `OccupancySummary` shape under `counts` and adds
// `free_codes_by_floor` / `plate_search_enabled` beside it - updated here to
// match, rather than the old flat shape the resident-tier `/summary` used.
const SUMMARY_OK = {
  counts: {
    total: 10,
    free: 6,
    occupied: 3,
    unknown: 1,
    by_floor: [{ floor: '1', total: 10, free: 6, occupied: 3, unknown: 1 }],
    updated_at: '2026-01-01T00:00:00Z',
  },
  free_codes_by_floor: { '1': ['A1', 'A2'] },
  plate_search_enabled: false,
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

  it('renders with no auth token in localStorage (anonymous)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, SUMMARY_OK))
    vi.stubGlobal('fetch', fetchMock)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <KioskPage />
      </QueryClientProvider>,
    )

    // Anonymous access works: the counts are displayed
    await waitFor(() => {
      expect(within(screen.getByRole('group', { name: 'Free' })).getByText('6')).toBeInTheDocument()
    })
  })

  it('shows free codes for a floor', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, SUMMARY_OK))
    vi.stubGlobal('fetch', fetchMock)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <KioskPage />
      </QueryClientProvider>,
    )

    await waitFor(() => {
      expect(screen.getByText('A1')).toBeInTheDocument()
    })
    expect(screen.getByText('A2')).toBeInTheDocument()
  })

  it('never renders an occupied code passed in a hand-built payload', async () => {
    const payloadWithOccupied = {
      counts: {
        total: 10,
        free: 5,
        occupied: 4,
        unknown: 1,
        by_floor: [{ floor: '1', total: 10, free: 5, occupied: 4, unknown: 1 }],
        updated_at: '2026-01-01T00:00:00Z',
      },
      free_codes_by_floor: { '1': ['A1', 'A2'] }, // Only free codes
      plate_search_enabled: false,
    }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, payloadWithOccupied))
    vi.stubGlobal('fetch', fetchMock)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <KioskPage />
      </QueryClientProvider>,
    )

    await waitFor(() => {
      expect(screen.getByText('A1')).toBeInTheDocument()
    })

    // Occupied codes should never appear in the response payload, but if they did,
    // this would catch any UI that naively renders all codes
    expect(screen.queryByText('A999')).not.toBeInTheDocument()
  })

  it('hides search input when plate_search_enabled is false', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, SUMMARY_OK))
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

    // The search box should not be rendered when plate_search_enabled=false
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument()
  })

  it('renders the disabled notice when PUBLIC_KIOSK_DISABLED is returned', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse(404, {
          error: {
            code: 'PUBLIC_KIOSK_DISABLED',
            message: 'The public kiosk is not enabled on this server',
            request_id: 'test-id',
            details: {},
          },
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <KioskPage />
      </QueryClientProvider>,
    )

    await waitFor(() => {
      expect(screen.getByText(/not enabled/i)).toBeInTheDocument()
    })
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

    await queryClient.refetchQueries({ queryKey: queryKeys.publicKiosk.summary() })

    await waitFor(() => {
      expect(screen.getByText('Offline')).toBeInTheDocument()
    })
    // The numbers from the last successful poll are still on screen.
    expect(within(screen.getByRole('group', { name: 'Free' })).getByText('6')).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Occupied' })).getByText('3')).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Unknown' })).getByText('1')).toBeInTheDocument()
  })

  // A site whose floors are named "1"/"2" rendered a lone digit above the
  // counts, which on a lobby screen reads as a fourth number rather than as
  // the floor the other three describe.
  it('labels the floor rather than printing its bare code', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, SUMMARY_OK)))

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <KioskPage />
      </QueryClientProvider>,
    )

    await waitFor(() => {
      expect(screen.getByText('Floor 1')).toBeInTheDocument()
    })
  })

  /**
   * A full floor must say so in words. The counts alone leave a green `0`
   * standing where the free-bay codes normally are, and a driver reading it
   * across a lobby is deciding whether to drive down at all.
   */
  it('says a floor is full instead of leaving a bare zero', async () => {
    const full = {
      counts: {
        total: 3,
        free: 0,
        occupied: 3,
        unknown: 0,
        by_floor: [{ floor: '1', total: 3, free: 0, occupied: 3, unknown: 0 }],
        updated_at: '2026-01-01T00:00:00Z',
      },
      // What the backend actually sends for a full floor: no free bay has a
      // code to list, so the floor is absent from the map entirely.
      free_codes_by_floor: {},
      plate_search_enabled: false,
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, full)))

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <KioskPage />
      </QueryClientProvider>,
    )

    await waitFor(() => {
      expect(screen.getByText('No free bays on this floor')).toBeInTheDocument()
    })
    // The counts still stand beside the sentence, and the free-bay heading is
    // gone rather than sitting above an empty row.
    expect(within(screen.getByRole('group', { name: 'Occupied' })).getByText('3')).toBeInTheDocument()
    expect(screen.queryByText('Free bays')).not.toBeInTheDocument()
  })
})
