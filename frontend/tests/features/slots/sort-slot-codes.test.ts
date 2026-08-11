import { describe, expect, it } from 'vitest'

import { compareSlotCodes, sortSlots } from '@/features/slots/sort-slot-codes'

describe('compareSlotCodes', () => {
  it('sorts numerically embedded in the code, not character-by-character', () => {
    const codes = ['A10', 'A2', 'A1']
    expect([...codes].sort(compareSlotCodes)).toEqual(['A1', 'A2', 'A10'])
  })

  it('is case-insensitive', () => {
    expect(compareSlotCodes('a1', 'A1')).toBe(0)
  })
})

describe('sortSlots', () => {
  it('sorts by floor first, then by natural-sorted code within the floor', () => {
    const slots = [
      { floor: '2', code: 'B1' },
      { floor: '1', code: 'A10' },
      { floor: '1', code: 'A2' },
      { floor: '1', code: 'A1' },
    ]

    expect(sortSlots(slots)).toEqual([
      { floor: '1', code: 'A1' },
      { floor: '1', code: 'A2' },
      { floor: '1', code: 'A10' },
      { floor: '2', code: 'B1' },
    ])
  })

  it('does not mutate the input array', () => {
    const slots = [{ floor: '1', code: 'A2' }, { floor: '1', code: 'A1' }]
    const original = [...slots]
    sortSlots(slots)
    expect(slots).toEqual(original)
  })
})
