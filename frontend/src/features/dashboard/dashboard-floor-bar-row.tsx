import { Flex, Typography } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { SLOT_STATE_COLORS } from '@/core/theme/use-theme-config'
import type { FloorSummary } from '@/features/slots/use-slots-queries'

/**
 * One floor's occupied/free/unknown counts as a three-segment bar.
 *
 * Segment widths are percentages of `floor.total`; when `total` is 0 the
 * divisor falls back to 1 so the bar renders as an empty track instead of
 * dividing by zero (all three segments are 0-wide either way). Colour is
 * never the only signal - each segment's count is also printed as text
 * above the bar, and the bar itself carries a full text `aria-label` so the
 * same information reaches a screen reader.
 */
export function DashboardFloorBarRow({ floor }: { floor: FloorSummary }): ReactNode {
  const { t } = useTranslation('slot')
  const total = floor.total || 1

  const segments = [
    { key: 'occupied', value: floor.occupied, color: SLOT_STATE_COLORS.OCCUPIED, label: t('slot:occupied') },
    { key: 'free', value: floor.free, color: SLOT_STATE_COLORS.FREE, label: t('slot:free') },
    { key: 'unknown', value: floor.unknown, color: SLOT_STATE_COLORS.UNKNOWN, label: t('slot:unknown') },
  ] as const

  const countsText = segments.map((segment) => `${segment.label} ${segment.value}`).join(' · ')

  return (
    <div>
      <Flex justify="space-between" align="baseline">
        <Typography.Text strong>{floor.floor}</Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {countsText}
        </Typography.Text>
      </Flex>
      <div
        role="img"
        aria-label={`${floor.floor}: ${countsText}`}
        style={{ display: 'flex', height: 12, borderRadius: 6, overflow: 'hidden', marginTop: 4 }}
      >
        {segments.map((segment) => (
          <div
            key={segment.key}
            style={{ width: `${(segment.value / total) * 100}%`, background: segment.color }}
          />
        ))}
      </div>
    </div>
  )
}
