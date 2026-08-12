import { Card, Empty, Skeleton } from 'antd'
import dayjs from 'dayjs'
import { useMemo } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { DASHBOARD_CHART_POLL_MS } from '@/core/constants/ui-constants'
import { OccupancyLineChart } from '@/features/statistics/occupancy-line-chart'
import { toOccupancySeries, useHourlyStatsQuery } from '@/features/statistics/use-stats-queries'

const CHART_WINDOW_HOURS = 24

/**
 * Occupancy over the last 24 hours, from the same pre-aggregated
 * `hourly_stats` (SITE scope) the statistics page charts - never recomputed
 * from raw history on the client, which is exactly what pre-aggregation
 * exists to avoid.
 *
 * The window is frozen at mount and simply refetched on
 * `DASHBOARD_CHART_POLL_MS` (far slower than the headline counters - hourly
 * aggregates do not change fast enough to justify anything quicker), rather
 * than sliding forward every render - the same fixed-range-refetched-on-an-
 * interval shape `statistics-page.tsx`'s own range picker already uses.
 *
 * When there is no history yet this says so plainly instead of drawing a
 * flat line that would look like real data.
 */
export function DashboardOccupancyChart(): ReactNode {
  const { t } = useTranslation('dashboard')
  const range = useMemo(
    () => ({ from: dayjs().subtract(CHART_WINDOW_HOURS, 'hour').toISOString(), to: dayjs().toISOString() }),
    [],
  )
  const { data, isLoading } = useHourlyStatsQuery('site', '', range, {
    refetchInterval: DASHBOARD_CHART_POLL_MS,
  })
  const series = useMemo(() => toOccupancySeries(data ?? []), [data])

  return (
    <Card title={t('dashboard:occupancyChartTitle')}>
      {isLoading ? (
        <Skeleton active />
      ) : series.length === 0 ? (
        <Empty description={t('dashboard:occupancyChartEmpty')} />
      ) : (
        <OccupancyLineChart data={series} />
      )}
    </Card>
  )
}
