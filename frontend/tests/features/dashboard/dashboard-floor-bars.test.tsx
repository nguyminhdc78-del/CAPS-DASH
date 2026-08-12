import '@/core/i18n/i18n-config'

import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import i18n from '@/core/i18n/i18n-config'
import { DashboardFloorBars } from '@/features/dashboard/dashboard-floor-bars'
import type { FloorSummary } from '@/features/slots/use-slots-queries'

function floor(code: string): FloorSummary {
  return { floor: code, total: 4, free: 2, occupied: 1, unknown: 1 }
}

/**
 * Guards the natural-sort requirement: floor labels sort the way a person
 * reading a parking sign expects (`L2` before `L10`), not the way a plain
 * string compare would order them (`L10` before `L2`, since '1' < '2'
 * character-by-character). Uses `compareSlotCodes`, the same natural-sort
 * helper the slots grid and the kiosk already sort floors with.
 */
describe('DashboardFloorBars', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('sorts floors naturally, not alphabetically', () => {
    const scrambled = ['L10', 'B2', 'G', 'L2', 'B1', 'L1'].map(floor)
    render(<DashboardFloorBars floors={scrambled} loading={false} />)

    const labels = screen.getAllByText(/^(B1|B2|G|L1|L2|L10)$/).map((el) => el.textContent)
    expect(labels).toEqual(['B1', 'B2', 'G', 'L1', 'L2', 'L10'])
  })
})
