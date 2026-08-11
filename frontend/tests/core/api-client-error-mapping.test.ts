import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/core/api/api-error'
import { api } from '@/core/api/api-client'
import { authTokenStore } from '@/core/api/auth-token-store'
import { resetRefreshStateForTests } from '@/core/api/refresh-single-flight'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: '',
    json: () => Promise.resolve(body),
  } as Response
}

describe('apiRequest', () => {
  beforeEach(() => {
    resetRefreshStateForTests()
    authTokenStore.clear()
  })

  it('parses the error envelope into an ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(409, {
          error: {
            code: 'CONFLICT',
            message: 'camera code already exists',
            request_id: 'req-1',
            details: { field: 'code' },
          },
        }),
      ),
    )

    const error = await api.get('/cameras').catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(ApiError)
    const apiError = error as ApiError
    expect(apiError.code).toBe('CONFLICT')
    expect(apiError.status).toBe(409)
    expect(apiError.requestId).toBe('req-1')
    expect(apiError.details).toEqual({ field: 'code' })
  })

  it('falls back to a status-derived code when the body is not our envelope', async () => {
    // A reverse proxy returning HTML must still produce something actionable
    // rather than a JSON parse crash.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: () => Promise.reject(new SyntaxError('not json')),
      } as unknown as Response),
    )

    const error = (await api.get('/nope').catch((caught: unknown) => caught)) as ApiError
    expect(error.code).toBe('NOT_FOUND')
  })

  it('attaches the bearer token when one is held', async () => {
    authTokenStore.set('token-123')
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    await api.get('/auth/me')

    const firstCall = fetchMock.mock.calls[0]
    expect(firstCall).toBeDefined()
    const headers = (firstCall?.[1] as RequestInit | undefined)?.headers as Headers
    expect(headers.get('Authorization')).toBe('Bearer token-123')
  })

  it('refreshes once and replays the request on 401', async () => {
    const fetchMock = vi
      .fn()
      // original request
      .mockResolvedValueOnce(jsonResponse(401, { error: { code: 'AUTH_TOKEN_EXPIRED' } }))
      // the refresh call
      .mockResolvedValueOnce(jsonResponse(200, { access_token: 'new-token' }))
      // the replay
      .mockResolvedValueOnce(jsonResponse(200, { username: 'guard' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.get('/auth/me')).resolves.toEqual({ username: 'guard' })
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(authTokenStore.get()).toBe('new-token')
  })

  it('does not retry forever when the refresh also fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { error: { code: 'AUTH_TOKEN_EXPIRED' } }))
      .mockResolvedValueOnce(jsonResponse(401, {}))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.get('/auth/me')).rejects.toBeInstanceOf(ApiError)
    // Original + refresh, and then it stops.
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('returns undefined for 204 rather than trying to parse a body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 204, json: () => Promise.reject() } as unknown as Response),
    )
    await expect(api.delete('/auth/sessions/1')).resolves.toBeUndefined()
  })
})
