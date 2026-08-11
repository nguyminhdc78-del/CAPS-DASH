import { describe, expect, it } from 'vitest'

import { hasAtLeastRole, rankOf } from '@/core/auth/role-ranking'

describe('role ranking', () => {
  it('lets a higher role do everything a lower one can', () => {
    // The whole point of ranking rather than equality: routes declare one
    // minimum instead of enumerating every role that qualifies.
    expect(hasAtLeastRole('admin', 'security')).toBe(true)
    expect(hasAtLeastRole('admin', 'resident')).toBe(true)
    expect(hasAtLeastRole('security', 'resident')).toBe(true)
  })

  it('refuses a lower role', () => {
    expect(hasAtLeastRole('resident', 'security')).toBe(false)
    expect(hasAtLeastRole('security', 'admin')).toBe(false)
  })

  it('accepts an exact match', () => {
    expect(hasAtLeastRole('security', 'security')).toBe(true)
  })

  it('treats missing or unknown roles as no privilege at all', () => {
    expect(rankOf(null)).toBe(0)
    expect(rankOf(undefined)).toBe(0)
    expect(rankOf('superuser')).toBe(0)
    expect(hasAtLeastRole('superuser', 'resident')).toBe(false)
  })
})
