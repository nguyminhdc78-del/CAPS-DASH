import { theme } from 'antd'

import { SLOT_STATE_COLORS } from '@/core/theme/use-theme-config'

export interface ChartPalette {
  occupied: string
  free: string
  unknown: string
  grid: string
  axis: string
  tooltipBackground: string
  tooltipBorder: string
}

/**
 * Antd design tokens -> Recharts colours.
 *
 * Reads `theme.useToken()` rather than hardcoding hex values, so every
 * chart follows the app's light/dark toggle automatically instead of
 * needing its own theme switch. The occupied/free/unknown series reuse
 * `SLOT_STATE_COLORS` from `state-tag.tsx` on purpose: a red line on a
 * chart should mean the same thing a red slot badge means elsewhere in the
 * app, not a chart-local colour choice that happens to also be red.
 */
export function useChartPalette(): ChartPalette {
  const { token } = theme.useToken()
  return {
    occupied: SLOT_STATE_COLORS.OCCUPIED,
    free: SLOT_STATE_COLORS.FREE,
    unknown: SLOT_STATE_COLORS.UNKNOWN,
    grid: token.colorBorderSecondary,
    axis: token.colorTextSecondary,
    tooltipBackground: token.colorBgElevated,
    tooltipBorder: token.colorBorderSecondary,
  }
}
