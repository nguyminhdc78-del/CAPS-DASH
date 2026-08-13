import { describe, expect, it } from 'vitest'

import { formatPlateForDisplay } from '@/features/plates/format-plate-for-display'

describe('formatPlateForDisplay', () => {
  it('punctuates a five-digit plate the way it is painted', () => {
    // The guard is comparing this against a windscreen two metres away.
    expect(formatPlateForDisplay('30H83231')).toBe('30H-832.31')
  })

  it('leaves a four-digit plate without the dot', () => {
    // Both lengths are current on Vietnamese plates and only the older,
    // shorter one is painted without the group separator.
    expect(formatPlateForDisplay('29H1234')).toBe('29H-1234')
  })

  it('handles a two-letter series', () => {
    expect(formatPlateForDisplay('51LD12345')).toBe('51LD-123.45')
  })

  it('handles a letter-then-digit series', () => {
    expect(formatPlateForDisplay('30A112345')).toBe('30A1-123.45')
  })

  it('hands back anything it does not recognise untouched', () => {
    // A misread, a foreign plate, or a format this car park has not seen.
    // Shown plainly it is still readable; chopped at the wrong place it is
    // worse than no formatting at all.
    expect(formatPlateForDisplay('ABC123')).toBe('ABC123')
    expect(formatPlateForDisplay('')).toBe('')
  })
})
