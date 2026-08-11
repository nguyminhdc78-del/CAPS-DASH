import { Card, Flex, Typography } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { SLOT_STATE_COLORS } from '@/core/theme/use-theme-config'
import type { FloorSummary } from '@/features/slots/use-slots-queries'

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
 * One floor's occupancy, in numbers a person can read from across a lobby.
 *
 * `floor.floor` is a level label (e.g. "1", "B1"), not a slot code or a
 * camera name - `OccupancySummary` (the resident-tier schema) never
 * includes either, so there is nothing here that could leak past the
 * privacy boundary even by accident. See `kiosk-page.tsx`'s top comment for
 * the fuller rationale.
 */
export function KioskFloorPanel({ floor }: { floor: FloorSummary }): ReactNode {
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
      </Flex>
    </Card>
  )
}
