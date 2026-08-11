import '@/core/i18n/i18n-config'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { App as AntApp } from 'antd'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/core/i18n/i18n-config'
import { PurgePanel } from '@/features/system/purge-panel'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: '',
    json: () => Promise.resolve(body),
  } as Response
}

function renderPanel(): void {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <AntApp>
        <PurgePanel />
      </AntApp>
    </QueryClientProvider>,
  )
}

/**
 * Pins down the panel's one hard requirement: a real purge (`dry_run:
 * false`) must be unreachable until the operator both previews what would
 * be deleted AND types the exact confirmation word. See phase-13's
 * "Destructive operations get friction" note and `purge-panel.tsx`'s
 * docstring.
 */
describe('PurgePanel', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('keeps "Purge now" disabled until the confirm word is typed exactly, even after a preview', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      jsonResponse(200, { deleted_history_rows: 1200, deleted_alert_rows: 4, dry_run: true }),
    )
    vi.stubGlobal('fetch', fetchMock)

    renderPanel()

    fireEvent.click(screen.getByRole('button', { name: 'Preview (dry run)' }))

    await waitFor(() => {
      expect(screen.getByText('1200')).toBeInTheDocument()
    })

    const purgeButton = screen.getByRole('button', { name: /purge now/i })
    expect(purgeButton).toBeDisabled()

    const confirmInput = screen.getByLabelText('Type PURGE to confirm')
    fireEvent.change(confirmInput, { target: { value: 'purge' } })
    expect(purgeButton).toBeDisabled()

    fireEvent.change(confirmInput, { target: { value: 'not even close' } })
    expect(purgeButton).toBeDisabled()

    // Only the exact-case word arms the button - a real deletion should
    // never be one careless click away.
    fireEvent.change(confirmInput, { target: { value: 'PURGE' } })
    expect(purgeButton).toBeEnabled()

    // The armed button still only fires a real (non-dry-run) purge, never
    // a second preview.
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { deleted_history_rows: 1200, deleted_alert_rows: 4, dry_run: false }),
    )
    fireEvent.click(purgeButton)

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2)
    })
    const secondCall = fetchMock.mock.calls[1] as [string, RequestInit]
    const body = JSON.parse(String(secondCall[1].body)) as { dry_run: boolean }
    expect(body.dry_run).toBe(false)
  })

  it('re-locks the confirmation after changing the retention window, so a stale preview cannot be confirmed', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      jsonResponse(200, { deleted_history_rows: 50, deleted_alert_rows: 1, dry_run: true }),
    )
    vi.stubGlobal('fetch', fetchMock)

    renderPanel()

    fireEvent.click(screen.getByRole('button', { name: 'Preview (dry run)' }))
    await waitFor(() => {
      expect(screen.getByText('50')).toBeInTheDocument()
    })

    const confirmInput = screen.getByLabelText('Type PURGE to confirm')
    fireEvent.change(confirmInput, { target: { value: 'PURGE' } })
    expect(screen.getByRole('button', { name: /purge now/i })).toBeEnabled()

    // Changing the retention window invalidates the preview shown above.
    const retentionInput = screen.getByPlaceholderText('Retention (months)')
    fireEvent.change(retentionInput, { target: { value: '3' } })

    expect(screen.queryByRole('button', { name: /purge now/i })).not.toBeInTheDocument()
  })
})
