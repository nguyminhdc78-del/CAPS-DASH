import { Alert } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

interface ClockSuspectBannerProps {
  /** Historical usage (history/sessions/statistics): rows in the current
   * result that were flagged suspect. Omit or 0 hides the banner. */
  count?: number
  /** Live usage (system page): the board's clock is unsynced right now,
   * per `SystemInfoResponse.clock_suspect`. */
  active?: boolean
}

/**
 * Surfaces `clock_suspect`, never hides it.
 *
 * The target board has no battery-backed clock (`db/clock_guard.py`), so
 * rows written before the next NTP sync carry a wrong timestamp. Every page
 * that can be affected shows this rather than silently including - or
 * silently dropping - the affected rows. Two modes because the two callers
 * have genuinely different data: a historical count of already-written rows
 * (history/sessions/statistics) versus "is the clock suspect right now"
 * (system page, which has no historical count to show).
 */
export function ClockSuspectBanner({ count, active }: ClockSuspectBannerProps): ReactNode {
  const { t } = useTranslation(['common', 'system'])
  const visible = active === true || (count ?? 0) > 0
  if (!visible) return null

  return (
    <Alert
      type="warning"
      showIcon
      message={t('common:clockSuspectBannerTitle')}
      description={
        active ? t('system:clockSuspectWarning') : t('common:clockSuspectBannerBody', { count })
      }
    />
  )
}
