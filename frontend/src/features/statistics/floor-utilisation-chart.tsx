import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { useChartPalette } from './chart-theme'

export interface FloorUtilisationPoint {
  floor: string
  utilisationPercent: number
}

/** One bar per floor: occupied seconds as a share of total seconds across
 * the selected range. Plain array in, presentational only. */
export function FloorUtilisationChart({ data }: { data: FloorUtilisationPoint[] }): ReactNode {
  const { t } = useTranslation('stats')
  const palette = useChartPalette()

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid stroke={palette.grid} strokeDasharray="3 3" />
        <XAxis dataKey="floor" stroke={palette.axis} />
        <YAxis stroke={palette.axis} unit="%" domain={[0, 100]} />
        <Tooltip
          contentStyle={{ background: palette.tooltipBackground, borderColor: palette.tooltipBorder }}
          formatter={(value) => [`${Number(value).toFixed(1)}%`, t('utilisation')]}
        />
        <Bar dataKey="utilisationPercent" name={t('utilisation')} fill={palette.occupied} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  )
}
