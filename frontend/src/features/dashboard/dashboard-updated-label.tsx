import { Typography } from 'antd'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * Quiet "updated Ns ago" text, ticking once a second so the count climbs
 * smoothly between polls instead of jumping in `SUMMARY_POLL_MS`-sized
 * steps. Same one-timer pattern `kiosk-page.tsx` uses for its clock, kept
 * local here since it is a single small interval for one caller - not worth
 * promoting to a shared hook.
 */
export function DashboardUpdatedLabel({ lastUpdatedAt }: { lastUpdatedAt: Date | null }): ReactNode {
  const { t } = useTranslation('dashboard')
  const [, forceTick] = useState(0)

  useEffect(() => {
    const id = setInterval(() => forceTick((n) => n + 1), 1_000)
    return () => clearInterval(id)
  }, [])

  if (lastUpdatedAt === null) return null

  const seconds = Math.max(0, Math.round((Date.now() - lastUpdatedAt.getTime()) / 1000))
  const label = seconds < 1 ? t('dashboard:updatedJustNow') : t('dashboard:updatedSecondsAgo', { seconds })

  return (
    <Typography.Text type="secondary" style={{ fontSize: 12 }} aria-live="polite">
      {label}
    </Typography.Text>
  )
}
