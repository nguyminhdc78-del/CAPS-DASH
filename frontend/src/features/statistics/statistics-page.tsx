import { App, Card, Col, Row, Skeleton, Space } from 'antd'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useErrorMessage } from '@/core/i18n/use-error-message'
import { HISTORY_DEFAULT_SPAN_DAYS } from '@/features/history/use-history-queries'
import { ClockSuspectBanner } from '@/features/system/clock-suspect-banner'
import { useFloorOptions } from '@/shared/hooks/use-parking-filter-options'
import { FloorUtilisationChart } from './floor-utilisation-chart'
import { OccupancyLineChart } from './occupancy-line-chart'
import { PeakHoursBarChart } from './peak-hours-bar-chart'
import { StatsRangePicker } from './stats-range-picker'
import {
  toFloorUtilisation,
  toOccupancySeries,
  toPeakHoursSeries,
  useFloorHourlyStatsQueries,
  useHourlyStatsQuery,
} from './use-stats-queries'

/** Occupancy over time, peak hours, and per-floor utilisation - all read
 * from the pre-aggregated `hourly_stats` table, never recomputed from raw
 * history on the client. */
export default function StatisticsPage(): ReactNode {
  const { t } = useTranslation('stats')
  const { message } = App.useApp()
  const toMessage = useErrorMessage()
  const floors = useFloorOptions()

  const [range, setRange] = useState<[Dayjs, Dayjs]>([
    dayjs().subtract(HISTORY_DEFAULT_SPAN_DAYS, 'day'),
    dayjs(),
  ])
  const statsRange = useMemo(() => ({ from: range[0].toISOString(), to: range[1].toISOString() }), [range])

  const site = useHourlyStatsQuery('site', '', statsRange)
  const floorQueries = useFloorHourlyStatsQueries(floors, statsRange)

  if (site.error) void message.error(toMessage(site.error))

  const occupancySeries = useMemo(() => toOccupancySeries(site.data ?? []), [site.data])
  const peakHoursSeries = useMemo(() => toPeakHoursSeries(site.data ?? []), [site.data])
  const floorUtilisation = useMemo(
    () => toFloorUtilisation(floors, floorQueries.map((query) => query.data ?? [])),
    [floors, floorQueries],
  )
  const suspectCount = (site.data ?? []).filter((row) => row.clock_suspect).length
  const floorsLoading = floorQueries.some((query) => query.isLoading)

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <ClockSuspectBanner count={suspectCount} />
      <StatsRangePicker value={range} onChange={setRange} />
      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card title={t('occupancyOverTime')}>
            {site.isLoading ? <Skeleton active /> : <OccupancyLineChart data={occupancySeries} />}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title={t('peakHours')}>
            {site.isLoading ? <Skeleton active /> : <PeakHoursBarChart data={peakHoursSeries} />}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title={t('floorUtilisation')}>
            {floorsLoading ? <Skeleton active /> : <FloorUtilisationChart data={floorUtilisation} />}
          </Card>
        </Col>
      </Row>
    </Space>
  )
}
