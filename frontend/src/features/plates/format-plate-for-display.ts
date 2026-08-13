/**
 * A stored plate, punctuated the way it is painted.
 *
 * Plates are stored with separators stripped (`30H83231`) so that searching
 * does not depend on which convention was typed. On screen the opposite is
 * true: a guard is comparing what they read against a windscreen two metres
 * away, and `30H-832.31` matches at a glance where `30H83231` has to be
 * spelled out character by character.
 *
 * Only the shape this car park actually sees is punctuated - two province
 * digits, a series letter, then four or five digits. Anything else is handed
 * back untouched rather than forced into a pattern it does not have: an
 * unfamiliar plate shown plainly is readable, and one chopped at the wrong
 * place is worse than no formatting at all.
 */
/**
 * The series digit is lazy (`\d??`) and the tail greedy on purpose. `30H83231`
 * splits two ways by character count alone - `30H` + `83231` or `30H8` +
 * `3231` - and the first is the real one. Preferring the longest tail picks
 * it, and still lets `30A112345` fall back to the four-character series
 * `30A1`, because six digits do not fit the tail.
 */
const VIETNAMESE_PLATE = /^(\d{2}[A-Z]{1,2}\d??)(\d{4,5})$/

export function formatPlateForDisplay(plate: string): string {
  const match = VIETNAMESE_PLATE.exec(plate)
  if (!match) return plate

  const prefix = match[1] ?? ''
  const digits = match[2] ?? ''
  // Five digits are painted `832.31`; four are painted plain. Both are current
  // on Vietnamese plates, and the dot is the only difference between them.
  const tail = digits.length === 5 ? `${digits.slice(0, 3)}.${digits.slice(3)}` : digits
  return `${prefix}-${tail}`
}
