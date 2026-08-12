import '@/core/i18n/i18n-config'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/core/i18n/i18n-config'
import { DashboardAlertsPanel } from '@/features/dashboard/dashboard-alerts-panel'

function jsonResponse(status: number, body: unknown): Response {
  return { ok: status >= 200 && status < 300, status, statusText: '', json: () => Promise.resolve(body) } as Response
}

/**
 * The phase brief is explicit: an empty "no alerts" card on the highest-
 * value screen in the app is wasted space, not reassurance - so when there
 * are zero open alerts this component must render nothing at all.
 */
describe('DashboardAlertsPanel', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('renders nothing when there are no open alerts', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(200, { items: [], total: 0, limit: 5, offset: 0 })),
    )
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <DashboardAlertsPanel />
      </QueryClientProvider>,
    )

    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })
})
