import '@/core/i18n/i18n-config'

import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import i18n from '@/core/i18n/i18n-config'
import { SlotCountStrip } from '@/features/slots/slot-count-strip'
import type { OccupancySummary, SlotRecord } from '@/features/slots/use-slots-queries'

function makeSlot(overrides: Partial<SlotRecord>): SlotRecord {
  return {
    id: overrides.id ?? 1,
    camera_id: 1,
    code: 'A1',
    floor: '1',
    current_state: 'FREE',
    state_since: null,
    is_active: true,
    ...overrides,
  }
}

/**
 * Pins down the one promise this component exists to keep: UNKNOWN is its
 * own number, never merged into FREE. See `state-tag.tsx` / the API's
 * `OccupancySummary` docstring for why that distinction matters.
 */
describe('SlotCountStrip', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('renders unknown as its own count, separate from and not added into free', () => {
    const rows: SlotRecord[] = [
      makeSlot({ id: 1, current_state: 'FREE' }),
      makeSlot({ id: 2, current_state: 'FREE' }),
      makeSlot({ id: 3, current_state: 'OCCUPIED' }),
      makeSlot({ id: 4, current_state: 'UNKNOWN' }),
    ]

    render(<SlotCountStrip rows={rows} summary={undefined} floor={null} />)

    const total = screen.getByRole('group', { name: 'Total slots' })
    const free = screen.getByRole('group', { name: 'Free' })
    const occupied = screen.getByRole('group', { name: 'Occupied' })
    const unknown = screen.getByRole('group', { name: 'Unknown' })

    expect(within(total).getByText('4')).toBeInTheDocument()
    expect(within(free).getByText('2')).toBeInTheDocument()
    expect(within(occupied).getByText('1')).toBeInTheDocument()
    expect(within(unknown).getByText('1')).toBeInTheDocument()
    // The unknown slot must never be silently counted as free.
    expect(within(free).queryByText('3')).not.toBeInTheDocument()
  })

  it('shows a refreshing hint, not a second set of numbers, when /summary disagrees', () => {
    const rows: SlotRecord[] = [makeSlot({ id: 1, current_state: 'FREE' })]
    const summary: OccupancySummary = {
      total: 5,
      free: 3,
      occupied: 1,
      unknown: 1,
      by_floor: [],
      updated_at: '2026-01-01T00:00:00Z',
    }

    render(<SlotCountStrip rows={rows} summary={summary} floor={null} />)

    expect(screen.getByText('Refreshing…')).toBeInTheDocument()
    // Summary's disagreeing numbers (3, 1) are not rendered as a second set.
    expect(screen.queryAllByText('3')).toHaveLength(0)
  })

  it('does not show the refreshing hint when the fetched rows agree with /summary', () => {
    const rows: SlotRecord[] = [makeSlot({ id: 1, current_state: 'FREE' })]
    const summary: OccupancySummary = {
      total: 1,
      free: 1,
      occupied: 0,
      unknown: 0,
      by_floor: [],
      updated_at: '2026-01-01T00:00:00Z',
    }

    render(<SlotCountStrip rows={rows} summary={summary} floor={null} />)

    expect(screen.queryByText('Refreshing…')).not.toBeInTheDocument()
  })
})
