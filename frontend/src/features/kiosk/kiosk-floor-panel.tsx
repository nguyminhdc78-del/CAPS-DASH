import { Card, Flex, Typography } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { SLOT_STATE_COLORS } from '@/core/theme/use-theme-config'
import type { FloorSummary } from '@/features/slots/use-slots-queries'
import { KioskFreeCodes } from './kiosk-free-codes'

// `clamp` rather than a fixed size: the same page runs on a lobby TV across
// the room and on a tablet by the barrier, and a number sized for one is
// unreadable or absurd on the other. The floor is the old fixed 56px, so a
// small screen loses nothing; the ceiling keeps a 4K wall from rendering a
// three-digit count wider than its panel.
function BigStat({ label, value, color }: { label: string; value: number; color: string }): ReactNode {
  return (
    <Flex vertical align="center" gap={4} role="group" aria-label={label}>
      <Typography.Text style={{ fontSize: 'clamp(18px, 1.6vw, 28px)' }}>{label}</Typography.Text>
      <Typography.Text
        style={{
          fontSize: 'clamp(56px, 7vw, 120px)',
          fontWeight: 700,
          lineHeight: 1,
          color,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {value}
      </Typography.Text>
    </Flex>
  )
}

/**
 * One floor's occupancy, in numbers a person can read from across a lobby,
 * plus the list of FREE bay codes on that floor.
 *
 * FREE codes are shown deliberately, not withheld: an empty bay holds no
 * car, so a code here identifies a space, not a vehicle - there is nothing
 * to protect by hiding it, and it is the whole point of the public kiosk
 * (find an open bay without walking every floor). Occupied and unknown
 * codes are still never sent by the backend and never rendered here; only
 * `free_codes_by_floor` carries a slot code at all. See `kiosk-page.tsx`'s
 * top comment for the fuller privacy rationale, including why plate search
 * (not this list) is where the real risk lives.
 */
export function KioskFloorPanel({
  floor,
  freeCodes,
}: {
  floor: FloorSummary
  freeCodes: string[]
}): ReactNode {
  const { t } = useTranslation('kiosk')

  return (
    <Card style={{ height: '100%' }} styles={{ body: { height: '100%' } }}>
      <Flex vertical align="center" justify="center" gap={16} style={{ height: '100%' }}>
        {/* "Tầng 1", not a bare "1". The backend stores the floor as a free
            text code, and a site that names its floors "1"/"2" rendered a
            lone digit above the counts - which reads as a count itself. */}
        <Typography.Title level={2} style={{ margin: 0 }}>
          {t('kiosk:floorLabel', { floor: floor.floor })}
        </Typography.Title>
        <Flex gap={40} wrap justify="center">
          <BigStat label={t('kiosk:free')} value={floor.free} color={SLOT_STATE_COLORS.FREE} />
          <BigStat label={t('kiosk:occupied')} value={floor.occupied} color={SLOT_STATE_COLORS.OCCUPIED} />
          <BigStat label={t('kiosk:unknown')} value={floor.unknown} color={SLOT_STATE_COLORS.UNKNOWN} />
        </Flex>
        <Typography.Text type="secondary">{t('kiosk:totalOfFloor', { total: floor.total })}</Typography.Text>
        {/* Said in words, not left to a green `0`. A driver reading this from
            across the lobby is deciding whether to drive down at all, and a
            zero among three other numbers is a worse answer than a sentence.
            Accurate even with UNKNOWN bays on the floor: an unknown bay is
            not a free one (see README, "UNKNOWN != FREE"), so there is
            genuinely nothing here to send a driver to. */}
        {floor.free === 0 ? (
          <Typography.Text style={{ fontSize: 'clamp(18px, 1.6vw, 28px)' }} strong>
            {t('kiosk:allFull')}
          </Typography.Text>
        ) : (
          <KioskFreeCodes codes={freeCodes} freeCount={floor.free} />
        )}
      </Flex>
    </Card>
  )
}
