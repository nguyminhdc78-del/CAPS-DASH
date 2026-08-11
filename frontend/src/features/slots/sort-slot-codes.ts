/**
 * Natural sort for slot floors and codes.
 *
 * `slot_service.list_slots` makes no ordering promise - the API contract
 * explicitly does not guarantee row order, so every consumer that renders a
 * slot list must sort client-side rather than trusting response order. A
 * plain string compare would put "A10" before "A2" (character-by-character,
 * '1' < '2'); `Intl.Collator`'s `numeric` mode compares embedded digit runs
 * as numbers instead, which is what "next to each other on the floor"
 * actually means to someone reading the grid.
 */

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })

/** Natural-order comparator for a single string field (floor OR code). */
export function compareSlotCodes(a: string, b: string): number {
  return collator.compare(a, b)
}

export interface SlotSortKey {
  floor: string
  code: string
}

/**
 * Sort by floor first, then by code within that floor - both natural-sorted.
 * Returns a new array; never mutates the input, since the input is usually
 * the array a TanStack Query cache entry still owns.
 */
export function sortSlots<T extends SlotSortKey>(slots: readonly T[]): T[] {
  return [...slots].sort(
    (a, b) => compareSlotCodes(a.floor, b.floor) || compareSlotCodes(a.code, b.code),
  )
}
