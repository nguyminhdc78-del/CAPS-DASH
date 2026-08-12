import '@/core/i18n/i18n-config'

import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import i18n from '@/core/i18n/i18n-config'
import { DashboardHeadlineCounters } from '@/features/dashboard/dashboard-headline-counters'
import type { OccupancySummary } from '@/features/slots/use-slots-queries'

/**
 * Pins down the same promise `slot-count-strip.test.tsx` pins down for the
 * slots page: UNKNOWN is its own number, never folded into FREE. See
 * `use-slots-queries.ts::OccupancySummary`'s docstring - a slot the detector
 * cannot currently classify is a different fact from an empty one.
 */
describe('DashboardHeadlineCounters', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('renders unknown as its own count, separate from and not added into free', () => {
    const summary: OccupancySummary = {
      total: 10,
      free: 6,
      occupied: 3,
      unknown: 1,
      by_floor: [],
      updated_at: '2026-01-01T00:00:00Z',
    }

    render(<DashboardHeadlineCounters summary={summary} loading={false} />)

    expect(within(screen.getByRole('group', { name: 'Total slots' })).getByText('10')).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Free' })).getByText('6')).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Occupied' })).getByText('3')).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Unknown' })).getByText('1')).toBeInTheDocument()
    // The unknown slot must never be silently counted as free.
    expect(within(screen.getByRole('group', { name: 'Free' })).queryByText('1')).not.toBeInTheDocument()
  })
})
