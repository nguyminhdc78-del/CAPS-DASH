import { createContext, useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { api, onAuthExpired } from '@/core/api/api-client'
import { authTokenStore } from '@/core/api/auth-token-store'
import { refreshAccessToken } from '@/core/api/refresh-single-flight'
import type { Role } from './role-ranking'

export interface CurrentUser {
  username: string
  display_name: string
  role: Role
}

/**
 * 'booting' exists so guarded routes never flash the login page at a user who
 * is in fact signed in. On a cold load we hold a refresh cookie but no access
 * token yet, and until that exchange finishes the answer is genuinely unknown.
 */
export type AuthStatus = 'booting' | 'authenticated' | 'anonymous'

export interface AuthContextValue {
  user: CurrentUser | null
  status: AuthStatus
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

interface LoginResponse {
  access_token: string
  user: CurrentUser
}

export function AuthProvider({ children }: { children: ReactNode }): ReactNode {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [status, setStatus] = useState<AuthStatus>('booting')

  // Cold start: try to trade the httpOnly refresh cookie for an access token.
  useEffect(() => {
    let cancelled = false

    void (async () => {
      const refreshed = await refreshAccessToken()
      if (cancelled) return
      if (!refreshed) {
        setStatus('anonymous')
        return
      }
      try {
        const me = await api.get<CurrentUser>('/auth/me')
        if (cancelled) return
        setUser(me)
        setStatus('authenticated')
      } catch {
        if (!cancelled) setStatus('anonymous')
      }
    })()

    return () => {
      cancelled = true
    }
  }, [])

  // The API layer shouts when a refresh finally fails; react to it here rather
  // than letting every caller handle session death on its own.
  useEffect(
    () =>
      onAuthExpired(() => {
        authTokenStore.clear()
        setUser(null)
        setStatus('anonymous')
      }),
    [],
  )

  const login = useCallback(async (username: string, password: string) => {
    const result = await api.post<LoginResponse>('/auth/login', { username, password })
    authTokenStore.set(result.access_token)
    setUser(result.user)
    setStatus('authenticated')
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout')
    } finally {
      // Local state clears even if the call failed - a user who pressed logout
      // must not be left looking at an authenticated screen.
      authTokenStore.clear()
      setUser(null)
      setStatus('anonymous')
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ user, status, login, logout }),
    [user, status, login, logout],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}
