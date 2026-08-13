import { theme } from 'antd'
import type { ThemeConfig } from 'antd'

/**
 * The kiosk forces its own dark "HUD" theme regardless of the admin theme
 * toggle: it is a public tech display, often on a wall in a dim garage, and a
 * light admin session must not turn the lobby screen white. Neon cyan accent
 * on deep navy; the glow/scan effects live in droom.css, this only carries the
 * AntD tokens (dark algorithm, accent, larger kiosk-distance control sizing).
 */
export const KIOSK_HUD_THEME: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#22d3ee',
    colorInfo: '#22d3ee',
    colorSuccess: '#22c55e',
    colorError: '#f87171',
    colorBgBase: '#060b18',
    colorText: '#e2f2ff',
    colorTextSecondary: '#7c93b4',
    borderRadius: 14,
    fontSize: 16,
    controlHeightLG: 56,
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  },
}
