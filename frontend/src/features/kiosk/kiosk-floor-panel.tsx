import { Card, Flex, Typography } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { SLOT_STATE_COLORS } from '@/core/theme/use-theme-config'
import type { FloorSummary } from '@/features/slots/use-slots-queries'
import { KioskFreeCodes } from './kiosk-free-codes'

function BigStat({ label, value, color }: { label: string; value: number; color: string }): ReactNode {
  return (
    <Flex vertical align="center" gap={4} role="group" aria-label={label}>
      <Typography.Text style={{ fontSize: 18 }}>{label}</Typography.Text>
      <Typography.Text style={{ fontSize: 56, fontWeight: 700, lineHeight: 1, color }}>
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
    <Card>
      <Flex vertical align="center" gap={16}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          {floor.floor}
        </Typography.Title>
        <Flex gap={40} wrap justify="center">
          <BigStat label={t('kiosk:free')} value={floor.free} color={SLOT_STATE_COLORS.FREE} />
          <BigStat label={t('kiosk:occupied')} value={floor.occupied} color={SLOT_STATE_COLORS.OCCUPIED} />
          <BigStat label={t('kiosk:unknown')} value={floor.unknown} color={SLOT_STATE_COLORS.UNKNOWN} />
        </Flex>
        <Typography.Text type="secondary">{t('kiosk:totalOfFloor', { total: floor.total })}</Typography.Text>
        <KioskFreeCodes codes={freeCodes} freeCount={floor.free} />
      </Flex>
    </Card>
  )
}
