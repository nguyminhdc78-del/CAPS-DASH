import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { useChartPalette } from './chart-theme'

export interface PeakHourPoint {
  hourOfDay: number
  occupiedPercent: number
}

/** Average occupancy by hour-of-day (0-23), averaged across every day in
 * the selected range - shows when the site tends to be busiest regardless
 * of which calendar day. Plain array in, presentational only. */
export function PeakHoursBarChart({ data }: { data: PeakHourPoint[] }): ReactNode {
  const { t } = useTranslation('stats')
  const palette = useChartPalette()

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid stroke={palette.grid} strokeDasharray="3 3" />
        <XAxis dataKey="hourOfDay" stroke={palette.axis} tickFormatter={(value: number) => `${value}h`} />
        <YAxis stroke={palette.axis} unit="%" domain={[0, 100]} />
        <Tooltip
          contentStyle={{ background: palette.tooltipBackground, borderColor: palette.tooltipBorder }}
          labelFormatter={(value) => `${String(value)}:00`}
          formatter={(value) => [`${Number(value).toFixed(1)}%`, t('occupancy')]}
        />
        <Bar dataKey="occupiedPercent" name={t('occupancy')} fill={palette.occupied} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  )
}
