import dayjs from 'dayjs'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { useChartPalette } from './chart-theme'

export interface OccupancyPoint {
  hour: string
  occupiedPercent: number
}

/**
 * Occupancy over time, from `hourly_stats` (SITE scope) - never recomputed
 * from raw history, which is exactly what pre-aggregation exists to avoid.
 * Receives an already-transformed plain array (see
 * `use-stats-queries.ts::toOccupancySeries`); this component only renders.
 */
export function OccupancyLineChart({ data }: { data: OccupancyPoint[] }): ReactNode {
  const { t } = useTranslation('stats')
  const palette = useChartPalette()

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid stroke={palette.grid} strokeDasharray="3 3" />
        <XAxis
          dataKey="hour"
          stroke={palette.axis}
          tickFormatter={(value: string) => dayjs(value).format('MM-DD HH:mm')}
          minTickGap={32}
        />
        <YAxis stroke={palette.axis} unit="%" domain={[0, 100]} />
        <Tooltip
          contentStyle={{ background: palette.tooltipBackground, borderColor: palette.tooltipBorder }}
          labelFormatter={(value) => dayjs(String(value)).format('YYYY-MM-DD HH:mm')}
          formatter={(value) => [`${Number(value).toFixed(1)}%`, t('occupancy')]}
        />
        <Line
          type="monotone"
          dataKey="occupiedPercent"
          name={t('occupancy')}
          stroke={palette.occupied}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
