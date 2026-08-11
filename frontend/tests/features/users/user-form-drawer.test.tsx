import '@/core/i18n/i18n-config'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/core/i18n/i18n-config'
import { UserFormDrawer } from '@/features/users/user-form-drawer'
import type { UserAccount } from '@/features/users/use-users-queries'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: '',
    json: () => Promise.resolve(body),
  } as Response
}

function renderDrawer(user: UserAccount | null): ReactElement {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  const ui = (
    <QueryClientProvider client={queryClient}>
      <UserFormDrawer open user={user} onClose={() => {}} />
    </QueryClientProvider>
  )
  render(ui)
  return ui
}

const LAST_ADMIN: UserAccount = {
  id: 1,
  username: 'admin',
  display_name: 'Admin',
  role: 'admin',
  is_active: true,
  last_login_at: null,
  created_at: '2026-01-01T00:00:00Z',
}

describe('UserFormDrawer', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('fires client-side validation and never calls the API', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    renderDrawer(null)

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(screen.getByText('Enter a username')).toBeInTheDocument()
    })
    expect(screen.getByText('Enter a password')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('surfaces USER_LAST_ADMIN as a readable message, not a generic failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(422, {
          error: {
            code: 'USER_LAST_ADMIN',
            message: 'This is the last active administrator',
            request_id: 'req-1',
            details: {},
          },
        }),
      ),
    )

    renderDrawer(LAST_ADMIN)

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      // From errors.json, keyed off the code - not the backend's raw
      // developer-facing "message" field.
      expect(screen.getByText(/last active administrator/i)).toBeInTheDocument()
    })
    expect(screen.queryByText('This is the last active administrator')).not.toBeInTheDocument()
  })
})
