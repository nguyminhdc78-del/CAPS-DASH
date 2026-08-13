import '@/core/i18n/i18n-config'

import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it } from 'vitest'

import i18n from '@/core/i18n/i18n-config'
import { PlateMatchCard } from '@/features/plates/plate-match-card'
import type { PlateMatch } from '@/features/plates/use-plate-search-query'

function makeMatch(overrides: Partial<PlateMatch> = {}): PlateMatch {
  return {
    plate: '30H83231',
    slot_code: 'B12',
    floor: 'B1',
    camera_id: 1,
    camera_code: 'CAM-1',
    slot_state: 'OCCUPIED',
    read_at: '2026-08-13T09:15:00Z',
    confidence: 0.91,
    plate_width_px: 150,
    ...overrides,
  }
}

function renderCard(match: PlateMatch) {
  return render(
    <MemoryRouter>
      <PlateMatchCard match={match} />
    </MemoryRouter>,
  )
}

describe('PlateMatchCard', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('shows the bay, which is the answer the guard came for', () => {
    renderCard(makeMatch())

    expect(screen.getByText('B12')).toBeInTheDocument()
    expect(screen.getByText('B1')).toBeInTheDocument()
  })

  it('punctuates the plate the way it is painted', () => {
    renderCard(makeMatch())

    expect(screen.getByText('30H-832.31')).toBeInTheDocument()
  })

  it('marks a low-confidence reading as one to check', () => {
    /* A 0.31 reading passes the backend floor but is a lead, not a fact.
       Shown identically to a 0.91 reading, a guard would tell a resident
       their car is in B12 on the strength of a guess. */
    renderCard(makeMatch({ confidence: 0.31, plate_width_px: 62 }))

    expect(screen.getByText('Check this one')).toBeInTheDocument()
  })

  it('does not nag about a confident reading', () => {
    renderCard(makeMatch())

    expect(screen.queryByText('Check this one')).not.toBeInTheDocument()
  })

  it('says so when the bay has since emptied', () => {
    /* Only reachable via the explicit "include vacated" toggle, and the
       whole point of that answer is that it is historical - a guard sent to
       an empty bay without being told would trust it and walk there. */
    renderCard(makeMatch({ slot_state: 'FREE' }))

    expect(screen.getByText('Bay now empty')).toBeInTheDocument()
  })

  it('links to the live view of the camera that saw it', () => {
    renderCard(makeMatch())

    expect(screen.getByRole('link')).toHaveAttribute('href', '/cameras/CAM-1/live')
  })
})
