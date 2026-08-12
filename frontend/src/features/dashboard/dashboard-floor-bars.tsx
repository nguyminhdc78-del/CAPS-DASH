import { Card, Empty, Flex, Skeleton } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { compareSlotCodes } from '@/features/slots/sort-slot-codes'
import type { FloorSummary } from '@/features/slots/use-slots-queries'
import { DashboardFloorBarRow } from './dashboard-floor-bar-row'

/**
 * One row per floor from `/summary`'s `by_floor`, natural-sorted - `B2, B1,
 * G, L1, L2, L10` in floor-label order, never the alphabetical sort that
 * would put `L10` before `L2`. Reuses `compareSlotCodes`, the same
 * natural-sort helper the slots grid and the kiosk already sort floors
 * with, rather than a second implementation living here.
 *
 * Shown to every role: `FloorSummary` (like `OccupancySummary`) carries
 * counts only - no slot code, no camera - so there is nothing here a
 * resident should not see.
 */
export function DashboardFloorBars({
  floors,
  loading,
}: {
  floors: FloorSummary[]
  loading: boolean
}): ReactNode {
  const { t } = useTranslation(['dashboard', 'kiosk'])
  const sorted = [...floors].sort((a, b) => compareSlotCodes(a.floor, b.floor))

  return (
    <Card title={t('dashboard:floorBarsTitle')}>
      {loading ? (
        <Skeleton active paragraph={{ rows: 3 }} />
      ) : sorted.length === 0 ? (
        <Empty description={t('kiosk:noFloorData')} />
      ) : (
        <Flex vertical gap={16}>
          {sorted.map((floor) => (
            <DashboardFloorBarRow key={floor.floor} floor={floor} />
          ))}
        </Flex>
      )}
    </Card>
  )
}
