import { useQuery } from '@tanstack/react-query'
import { Alert, Card, Col, Row, Statistic } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { api } from '@/core/api/api-client'
import { SLOT_STATE_COLORS } from '@/core/theme/use-theme-config'

interface OccupancySummary {
  total: number
  free: number
  occupied: number
  unknown: number
  updated_at: number
}

/**
 * The summary every role may see.
 *
 * Counts only - which slot holds which car is private to residents and is
 * never sent to this endpoint. That privacy split is part of the original CAPS
 * API contract and is preserved deliberately.
 */
export default function DashboardPage(): ReactNode {
  const { t } = useTranslation(['slot', 'common'])

  const { data, isLoading, isError } = useQuery({
    queryKey: ['summary'],
    queryFn: () => api.get<OccupancySummary>('/summary'),
    // Slot state settles over seconds; polling faster only loads the board.
    refetchInterval: 3_000,
  })

  if (isError) {
    return <Alert type="error" showIcon message={t('common:unexpectedError')} />
  }

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} sm={12} lg={6}>
        <Card>
          <Statistic title={t('slot:total')} value={data?.total ?? 0} loading={isLoading} />
        </Card>
      </Col>
      <Col xs={24} sm={12} lg={6}>
        <Card>
          <Statistic
            title={t('slot:free')}
            value={data?.free ?? 0}
            loading={isLoading}
            valueStyle={{ color: SLOT_STATE_COLORS.FREE }}
          />
        </Card>
      </Col>
      <Col xs={24} sm={12} lg={6}>
        <Card>
          <Statistic
            title={t('slot:occupied')}
            value={data?.occupied ?? 0}
            loading={isLoading}
            valueStyle={{ color: SLOT_STATE_COLORS.OCCUPIED }}
          />
        </Card>
      </Col>
      <Col xs={24} sm={12} lg={6}>
        <Card>
          <Statistic
            title={t('slot:unknown')}
            value={data?.unknown ?? 0}
            loading={isLoading}
            valueStyle={{ color: SLOT_STATE_COLORS.UNKNOWN }}
          />
        </Card>
      </Col>

      {(data?.unknown ?? 0) > 0 && (
        <Col span={24}>
          {/* Said out loud rather than quietly folded into "free". */}
          <Alert type="info" showIcon message={t('slot:unknownNotFree')} />
        </Col>
      )}
    </Row>
  )
}
