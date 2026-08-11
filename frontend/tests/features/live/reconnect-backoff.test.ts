import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { nextBackoffDelayMs } from '@/features/live/reconnect-backoff'

describe('nextBackoffDelayMs', () => {
  beforeEach(() => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5) // jitter factor = 1.0 exactly
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('doubles from a 1s base with no jitter applied', () => {
    expect(nextBackoffDelayMs(0)).toBe(1000)
    expect(nextBackoffDelayMs(1)).toBe(2000)
    expect(nextBackoffDelayMs(2)).toBe(4000)
  })

  it('caps at 8s however high the attempt count goes', () => {
    expect(nextBackoffDelayMs(3)).toBe(8000)
    expect(nextBackoffDelayMs(10)).toBe(8000)
  })

  it('stays within the +/-25% jitter band around the exponential value', () => {
    vi.spyOn(Math, 'random').mockRestore()
    for (let attempt = 0; attempt < 5; attempt++) {
      const exponential = Math.min(8000, 1000 * 2 ** attempt)
      const delay = nextBackoffDelayMs(attempt)
      expect(delay).toBeGreaterThanOrEqual(Math.round(exponential * 0.75))
      expect(delay).toBeLessThanOrEqual(Math.round(exponential * 1.25))
    }
  })
})
