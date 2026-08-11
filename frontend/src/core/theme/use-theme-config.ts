import { theme } from 'antd'
import type { ThemeConfig } from 'antd'
import { useContext, useMemo } from 'react'

import { ThemeContext } from './theme-provider'

/** Slot-state colours, shared by tables, the grid and the live overlay. */
export const SLOT_STATE_COLORS = {
  FREE: '#52c41a',
  OCCUPIED: '#f5222d',
  // Deliberately grey, never a shade of green. UNKNOWN must not read as
  // "probably free" at a glance from across the security desk.
  UNKNOWN: '#8c8c8c',
} as const

export function useThemeConfig(): ThemeConfig {
  const context = useContext(ThemeContext)
  const mode = context?.mode ?? 'light'

  return useMemo<ThemeConfig>(
    () => ({
      algorithm: mode === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
      token: {
        colorPrimary: '#1677ff',
        borderRadius: 6,
        fontSize: 14,
      },
      components: {
        Layout: {
          headerHeight: 56,
        },
      },
    }),
    [mode],
  )
}

export function useThemeMode() {
  const context = useContext(ThemeContext)
  if (context === null) throw new Error('useThemeMode must be used inside <ThemeProvider>')
  return context
}
