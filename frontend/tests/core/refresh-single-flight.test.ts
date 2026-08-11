import { beforeEach, describe, expect, it, vi } from 'vitest'

import { authTokenStore } from '@/core/api/auth-token-store'
import {
  refreshAccessToken,
  resetRefreshStateForTests,
} from '@/core/api/refresh-single-flight'

describe('refreshAccessToken', () => {
  beforeEach(() => {
    resetRefreshStateForTests()
    authTokenStore.clear()
  })

  it('stores the new access token on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ access_token: 'fresh-token' }),
      }),
    )

    await expect(refreshAccessToken()).resolves.toBe(true)
    expect(authTokenStore.get()).toBe('fresh-token')
  })

  it('shares one request between concurrent callers', async () => {
    /**
     * The reason this module exists. Refresh tokens rotate, so a second
     * concurrent refresh would present a JTI the first call already rotated -
     * which the backend correctly reads as token theft and answers by revoking
     * every session the user has. Loading a page must not log someone out
     * everywhere.
     */
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ access_token: 'shared-token' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const results = await Promise.all([
      refreshAccessToken(),
      refreshAccessToken(),
      refreshAccessToken(),
    ])

    expect(results).toEqual([true, true, true])
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('allows a new attempt once the previous one settles', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ access_token: 'token' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await refreshAccessToken()
    await refreshAccessToken()

    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('clears the token when the refresh is rejected', async () => {
    authTokenStore.set('stale')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401 }))

    await expect(refreshAccessToken()).resolves.toBe(false)
    expect(authTokenStore.get()).toBeNull()
  })

  it('keeps the existing token when the network is simply down', async () => {
    // A dropped connection is not proof the session ended. Discarding the
    // token here would sign the user out every time wifi hiccups.
    authTokenStore.set('still-valid')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network')))

    await expect(refreshAccessToken()).resolves.toBe(false)
    expect(authTokenStore.get()).toBe('still-valid')
  })

  it('treats a success response with no token as a failure', async () => {
    authTokenStore.set('stale')
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) }),
    )

    await expect(refreshAccessToken()).resolves.toBe(false)
    expect(authTokenStore.get()).toBeNull()
  })
})
