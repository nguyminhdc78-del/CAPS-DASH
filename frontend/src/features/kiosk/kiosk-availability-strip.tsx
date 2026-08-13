import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { compareSlotCodes } from '@/features/slots/sort-slot-codes'
import type { FloorSummary } from '@/features/slots/use-slots-queries'

/** How many free-bay codes each compact floor card shows before it collapses
 *  the rest into a "+N" chip - a lobby strip has room for a hint, not the full
 *  40/floor list the availability-only board carries. */
const MAX_CODES_PER_FLOOR = 6

function FloorChip({
  floor,
  codes,
}: {
  floor: FloorSummary
  codes: string[]
}): ReactNode {
  const { t } = useTranslation('kiosk')
  const isFull = floor.free === 0
  const shown = [...codes].sort(compareSlotCodes).slice(0, MAX_CODES_PER_FLOOR)
  const extra = Math.max(0, codes.length - shown.length)

  return (
    <div className="kiosk-avail__floor" role="group" aria-label={t('kiosk:floorLabel', { floor: floor.floor })}>
      <div className="kiosk-avail__name">{t('kiosk:floorLabel', { floor: floor.floor })}</div>
      <div className={`kiosk-avail__free${isFull ? ' is-full' : ''}`}>{floor.free}</div>
      {/* Colour is never the only signal: the label spells out the state, and
          UNKNOWN is kept as its own number, never folded into free. */}
      <div className="kiosk-avail__meta">
        {isFull ? t('kiosk:allFull') : t('kiosk:free')}
        {' · '}
        {t('kiosk:occupied')} {floor.occupied} · {t('kiosk:unknown')} {floor.unknown}
      </div>
      {shown.length > 0 && (
        <div className="kiosk-avail__codes">
          {shown.map((code) => (
            <span key={code} className="kiosk-avail__code">
              {code}
            </span>
          ))}
          {extra > 0 && <span className="kiosk-avail__code">+{extra}</span>}
        </div>
      )}
    </div>
  )
}

/**
 * The occupancy board, demoted to a compact strip beneath the find-your-car
 * hero. Kept (not deleted) because it is a genuine second job of the kiosk -
 * an arriving driver looking for a free bay - and it is the *only* content
 * when the plate-search kill-switch is off. Each floor still shows all three
 * counts (free/occupied/unknown) and a hint of the free bay codes.
 */
export function KioskAvailabilityStrip({
  floors,
  freeCodesByFloor,
}: {
  floors: FloorSummary[]
  freeCodesByFloor: Record<string, string[]>
}): ReactNode {
  const sorted = [...floors].sort((a, b) => compareSlotCodes(a.floor, b.floor))
  if (sorted.length === 0) return null

  return (
    <div className="kiosk-avail">
      {sorted.map((floor) => (
        <FloorChip key={floor.floor} floor={floor} codes={freeCodesByFloor[floor.floor] ?? []} />
      ))}
    </div>
  )
}
