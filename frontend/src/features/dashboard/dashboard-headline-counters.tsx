import { Card, Col, Row, Skeleton, Statistic } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { SLOT_STATE_COLORS } from '@/core/theme/use-theme-config'
import type { OccupancySummary } from '@/features/slots/use-slots-queries'
import { useCountUp } from './use-count-up'

function CounterCard({
  label,
  value,
  color,
  loading,
}: {
  label: string
  value: number
  color?: string
  loading: boolean
}): ReactNode {
  const display = useCountUp(value)

  return (
    <Col xs={12} lg={6}>
      <Card>
        <div role="group" aria-label={label}>
          {loading ? (
            <Skeleton active paragraph={false} title={{ width: '60%' }} />
          ) : (
            // `valueStyle` prop omitted entirely (not passed as `undefined`)
            // when there is no colour - see the options-spread comment in
            // `use-cameras-queries.ts` for why exactOptionalPropertyTypes
            // requires that distinction.
            <Statistic title={label} value={display} {...(color ? { valueStyle: { color } } : {})} />
          )}
        </div>
      </Card>
    </Col>
  )
}

/**
 * Total / free / occupied / unknown - four independent numbers, large, with
 * a count-up animation on change (`useCountUp`).
 *
 * `unknown` gets its own card and its own colour (`SLOT_STATE_COLORS.
 * UNKNOWN`, grey), never summed into `free` and never rendered green. See
 * `use-slots-queries.ts::OccupancySummary`'s docstring: a slot the detector
 * cannot currently classify (camera offline, still warming up, occluded) is
 * a different fact from an empty one, and folding the two together would let
 * a stalled camera silently report itself as free parking.
 */
export function DashboardHeadlineCounters({
  summary,
  loading,
}: {
  summary: OccupancySummary | null
  loading: boolean
}): ReactNode {
  const { t } = useTranslation('slot')

  return (
    <Row gutter={[16, 16]}>
      <CounterCard label={t('slot:total')} value={summary?.total ?? 0} loading={loading} />
      <CounterCard
        label={t('slot:free')}
        value={summary?.free ?? 0}
        color={SLOT_STATE_COLORS.FREE}
        loading={loading}
      />
      <CounterCard
        label={t('slot:occupied')}
        value={summary?.occupied ?? 0}
        color={SLOT_STATE_COLORS.OCCUPIED}
        loading={loading}
      />
      <CounterCard
        label={t('slot:unknown')}
        value={summary?.unknown ?? 0}
        color={SLOT_STATE_COLORS.UNKNOWN}
        loading={loading}
      />
    </Row>
  )
}
