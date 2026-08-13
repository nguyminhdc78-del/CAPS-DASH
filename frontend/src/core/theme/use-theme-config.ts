import { theme } from 'antd'
import type { ThemeConfig } from 'antd'
import { useContext, useMemo } from 'react'

import { ThemeContext } from './theme-provider'

/** Slot-state colours, shared by tables, the grid and the live overlay.
 *  Aligned to the Droom accent palette (success/danger) while keeping the
 *  hard rule intact: UNKNOWN is a neutral slate, never a shade of green, so
 *  it can never read as "probably free" from across the security desk. */
export const SLOT_STATE_COLORS = {
  FREE: '#22c55e',
  OCCUPIED: '#ef4444',
  UNKNOWN: '#94a3b8',
} as const

/** Inter first, then the system stack so the page stays clean when the font
 *  CDN (or the kiosk) is offline. */
const FONT_FAMILY =
  "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"

export function useThemeConfig(): ThemeConfig {
  const context = useContext(ThemeContext)
  const mode = context?.mode ?? 'light'
  const isDark = mode === 'dark'

  return useMemo<ThemeConfig>(
    () => ({
      algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
      token: {
        colorPrimary: '#6366f1',
        colorInfo: '#6366f1',
        colorSuccess: '#22c55e',
        colorWarning: '#f59e0b',
        colorError: '#ef4444',
        colorLink: '#6366f1',
        colorLinkHover: '#4f46e5',
        borderRadius: 10,
        borderRadiusLG: 14,
        borderRadiusSM: 8,
        fontSize: 14,
        fontFamily: FONT_FAMILY,
        // Canvas + text tuned to the slate palette the stylesheet paints; the
        // radial-tinted body shows through the layout, header and content,
        // which are all left transparent so the glass effect reads.
        colorBgLayout: 'transparent',
        colorTextHeading: isDark ? '#f1f5f9' : '#1e293b',
        colorText: isDark ? '#cbd5e1' : '#334155',
        colorBorderSecondary: isDark ? '#334155' : '#e2e8f0',
        controlHeight: 38,
        controlHeightLG: 44,
      },
      components: {
        Layout: {
          headerHeight: 64,
          headerBg: 'transparent',
          bodyBg: 'transparent',
          siderBg: 'transparent',
        },
        Card: {
          borderRadiusLG: 16,
          paddingLG: 24,
        },
        Button: {
          fontWeight: 600,
          primaryShadow: 'none',
          defaultShadow: 'none',
        },
        Menu: {
          darkItemBg: 'transparent',
          darkSubMenuItemBg: 'transparent',
          darkItemSelectedBg: 'transparent',
        },
        Statistic: {
          contentFontSize: 30,
        },
      },
    }),
    [isDark],
  )
}

export function useThemeMode() {
  const context = useContext(ThemeContext)
  if (context === null) throw new Error('useThemeMode must be used inside <ThemeProvider>')
  return context
}
