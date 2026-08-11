import { Tag } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

/** Mirrors `AlertSeverity` in backend/caps_dash/db/enums.py. */
export type AlertSeverity = 'info' | 'warning' | 'critical'

const SEVERITY_COLOR: Record<AlertSeverity, string> = {
  info: 'blue',
  warning: 'orange',
  critical: 'red',
}

const SEVERITY_LABEL_KEY: Record<AlertSeverity, string> = {
  info: 'alert:severityInfo',
  warning: 'alert:severityWarning',
  critical: 'alert:severityCritical',
}

/** `AlertSeverity` -> colour + localized label, and nowhere else - mirrors
 * `state-tag.tsx`'s role for slot state. Falls back to `info` styling for
 * any value the frontend does not recognise, rather than rendering blank. */
export function AlertSeverityTag({ severity }: { severity: string }): ReactNode {
  const { t } = useTranslation('alert')
  const key: AlertSeverity = severity === 'warning' || severity === 'critical' ? severity : 'info'

  return <Tag color={SEVERITY_COLOR[key]}>{t(SEVERITY_LABEL_KEY[key])}</Tag>
}
