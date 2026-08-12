import '@/core/i18n/i18n-config'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthContext } from '@/core/auth/auth-context'
import type { AuthContextValue } from '@/core/auth/auth-context'
import i18n from '@/core/i18n/i18n-config'
import DashboardPage from '@/features/dashboard/dashboard-page'

function jsonResponse(status: number, body: unknown): Response {
  return { ok: status >= 200 && status < 300, status, statusText: '', json: () => Promise.resolve(body) } as Response
}

const SUMMARY_OK = {
  total: 10,
  free: 6,
  occupied: 3,
  unknown: 1,
  by_floor: [{ floor: '1', total: 10, free: 6, occupied: 3, unknown: 1 }],
  updated_at: '2026-01-01T00:00:00Z',
}

const RESIDENT_AUTH: AuthContextValue = {
  user: { username: 'resident1', display_name: 'Resident', role: 'resident' },
  status: 'authenticated',
  login: async () => {},
  logout: async () => {},
}

/**
 * Product rule, not a style choice: a resident sees counts and floor bars
 * only, never a camera name, a live frame or the camera-health strip - see
 * `dashboard-page.tsx`'s top comment. `/summary` (the one endpoint a
 * resident session can call) carries nothing more specific than counts, so
 * this also guards that the page never tries to reach `/cameras`,
 * `/alerts` or `/stats/hourly` for a role that cannot read them.
 */
describe('DashboardPage resident privacy', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('shows counts and floor bars only - no camera imagery, names or health for a resident', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, SUMMARY_OK))
    vi.stubGlobal('fetch', fetchMock)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <AuthContext value={RESIDENT_AUTH}>
          <DashboardPage />
        </AuthContext>
      </QueryClientProvider>,
    )

    await waitFor(() => {
      expect(within(screen.getByRole('group', { name: 'Free' })).getByText('6')).toBeInTheDocument()
    })

    // Floor bars ARE shown to residents.
    expect(screen.getByText('Overview')).toBeInTheDocument()

    // Staff-only blocks must not render at all.
    expect(screen.queryByText('Live camera')).not.toBeInTheDocument()
    expect(screen.queryByText('Camera health')).not.toBeInTheDocument()
    expect(document.querySelectorAll('img')).toHaveLength(0)
    expect(document.querySelectorAll('canvas')).toHaveLength(0)

    // Never a network call to a staff-only endpoint for this role.
    const calledPaths = fetchMock.mock.calls.map((call) => String(call[0]))
    expect(calledPaths.every((path) => !path.includes('/api/cameras'))).toBe(true)
    expect(calledPaths.every((path) => !path.includes('/api/alerts'))).toBe(true)
    expect(calledPaths.every((path) => !path.includes('/api/stats'))).toBe(true)
  })
})
